interface AgentSelectorProps {
  agents: string[];
  selectedAgent: string | null;
  onSelect: (agentId: string) => void;
  onRefresh: () => void;
  disabled?: boolean;
}

export function AgentSelector({
  agents,
  selectedAgent,
  onSelect,
  onRefresh,
  disabled = false,
}: AgentSelectorProps) {
  return (
    <div className="agent-selector">
      <label htmlFor="agent-select">Agent:</label>
      <select
        id="agent-select"
        value={selectedAgent || ''}
        onChange={(e) => onSelect(e.target.value)}
        disabled={disabled || agents.length === 0}
      >
        <option value="">
          {agents.length === 0 ? 'No agents available' : 'Select an agent'}
        </option>
        {agents.map((agent) => (
          <option key={agent} value={agent}>
            {agent}
          </option>
        ))}
      </select>
      <button
        onClick={onRefresh}
        disabled={disabled}
        className="refresh-button"
        title="Refresh agent list"
      >
        Refresh
      </button>
    </div>
  );
}
