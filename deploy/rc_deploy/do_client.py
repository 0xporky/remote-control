import asyncio
from typing import Any

import pydo


def _public_ipv4(droplet: dict[str, Any]) -> str | None:
    for net in (droplet.get("networks") or {}).get("v4", []) or []:
        if net.get("type") == "public" and net.get("ip_address"):
            return str(net["ip_address"])
    return None


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


class DOClient:
    def __init__(self, api_token: str) -> None:
        self._c = pydo.Client(token=api_token)

    async def domain_exists(self, domain: str) -> bool:
        def _call() -> bool:
            try:
                self._c.domains.get(domain_name=domain)
                return True
            except Exception as exc:
                if _status_code(exc) == 404:
                    return False
                raise

        return await asyncio.to_thread(_call)

    async def create_droplet(
        self,
        *,
        name: str,
        image: str,
        size: str,
        region: str,
        ssh_key_fp: str,
        user_data: str,
        poll_interval: float = 3.0,
        timeout: float = 180.0,
    ) -> tuple[str, str]:
        def _create() -> int:
            resp = self._c.droplets.create(
                body={
                    "name": name,
                    "region": region,
                    "size": size,
                    "image": image,
                    "ssh_keys": [ssh_key_fp],
                    "user_data": user_data,
                }
            )
            droplet = resp.get("droplet") if isinstance(resp, dict) else None
            if not droplet or "id" not in droplet:
                raise RuntimeError(f"Unexpected droplet create response: {resp!r}")
            return int(droplet["id"])

        droplet_id = await asyncio.to_thread(_create)

        async def _poll_once() -> tuple[bool, str | None]:
            def _get() -> dict[str, Any]:
                return self._c.droplets.get(droplet_id=droplet_id)

            resp = await asyncio.to_thread(_get)
            droplet = resp.get("droplet") if isinstance(resp, dict) else None
            if not droplet:
                return False, None
            ip = _public_ipv4(droplet)
            ready = droplet.get("status") == "active" and ip is not None
            return ready, ip

        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            ready, ip = await _poll_once()
            if ready and ip is not None:
                return str(droplet_id), ip
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(
                    f"Droplet {droplet_id} not active with public IPv4 within {timeout:.0f}s"
                )
            await asyncio.sleep(poll_interval)

    async def delete_droplet(self, droplet_id: str) -> None:
        def _call() -> None:
            self._c.droplets.destroy(droplet_id=int(droplet_id))

        await asyncio.to_thread(_call)

    async def _list_a_record(self, domain: str, subdomain: str) -> dict[str, Any] | None:
        def _list() -> list[dict[str, Any]]:
            resp = self._c.domains.list_records(domain_name=domain, per_page=200)
            return list(resp.get("domain_records") or []) if isinstance(resp, dict) else []

        records = await asyncio.to_thread(_list)
        for rec in records:
            if rec.get("type") == "A" and rec.get("name") == subdomain:
                return rec
        return None

    async def upsert_a_record(
        self, domain: str, subdomain: str, ip: str, ttl: int = 60
    ) -> None:
        existing = await self._list_a_record(domain, subdomain)

        def _update(record_id: int) -> None:
            self._c.domains.update_record(
                domain_name=domain,
                domain_record_id=record_id,
                body={"type": "A", "name": subdomain, "data": ip, "ttl": ttl},
            )

        def _create() -> None:
            self._c.domains.create_record(
                domain_name=domain,
                body={"type": "A", "name": subdomain, "data": ip, "ttl": ttl},
            )

        if existing:
            await asyncio.to_thread(_update, int(existing["id"]))
        else:
            await asyncio.to_thread(_create)

    async def delete_a_record(self, domain: str, subdomain: str) -> bool:
        existing = await self._list_a_record(domain, subdomain)
        if not existing:
            return False

        def _call(record_id: int) -> None:
            self._c.domains.delete_record(domain_name=domain, domain_record_id=record_id)

        await asyncio.to_thread(_call, int(existing["id"]))
        return True
