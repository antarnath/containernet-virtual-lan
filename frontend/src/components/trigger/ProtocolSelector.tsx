// Protocol dropdown. For now only HTTP is fully wired; the others are
// placeholders for future phases.

interface Props {
  value: string;
  onChange: (v: string) => void;
}

const PROTOCOLS = [
  { value: 'HTTP', label: 'HTTP' },
  { value: 'TCP', label: 'TCP (coming soon)' },
  { value: 'SQL', label: 'SQL (coming soon)' },
  { value: 'FILE', label: 'FILE (coming soon)' },
];

export default function ProtocolSelector({ value, onChange }: Props) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-panel2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
    >
      {PROTOCOLS.map((p) => (
        <option key={p.value} value={p.value}>
          {p.label}
        </option>
      ))}
    </select>
  );
}