import { Search } from "lucide-react";

export function SearchField(props: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <label className="search">
      <span className="sr-only">{props.label}</span>
      <Search size={16} aria-hidden="true" />
      <input
        className="field"
        type="search"
        maxLength={200}
        value={props.value}
        placeholder={props.label}
        onChange={(e) => props.onChange(e.target.value)}
      />
    </label>
  );
}

export function SelectField(props: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  options: [value: string, label: string][];
}) {
  return (
    <select
      className="field"
      aria-label={props.label}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">{props.label}</option>
      {props.options.map(([value, label]) => (
        <option key={value} value={value}>
          {label}
        </option>
      ))}
    </select>
  );
}
