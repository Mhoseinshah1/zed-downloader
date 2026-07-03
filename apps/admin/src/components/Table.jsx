import { useLang } from "../i18n";

// Minimal data table.
// columns: [{ key, title, render?: (row) => node }]
// rows: array of objects; rowKey: field name used as React key (default "id").
export default function Table({ columns, rows, rowKey = "id", emptyText }) {
  const { t } = useLang();

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="table__empty" colSpan={columns.length}>
                {emptyText || t("table.empty")}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
