import { StatusPill } from '../../../components/ui';
import type { Cell, Column } from '../types';

function renderCell(cell: Cell | undefined, column: Column) {
  if (cell === undefined) return null;
  if (typeof cell === 'object') return <StatusPill status={cell.status} label={cell.label} />;
  if (column.kind === 'mono') return <span className="mono">{cell}</span>;
  return cell;
}

export function DataTable({
  title,
  columns,
  rows,
}: {
  title?: string;
  columns: Column[];
  rows: Record<string, Cell>[];
}) {
  return (
    <figure className="data-table">
      {title && <figcaption className="data-table__title">{title}</figcaption>}
      <div className="data-table__scroll">
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={c.kind === 'num' ? 'num' : undefined}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c.key} className={c.kind === 'num' ? 'num' : undefined}>
                    {renderCell(row[c.key], c)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
