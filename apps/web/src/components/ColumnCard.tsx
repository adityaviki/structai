import { useState } from "react";
import type { components } from "../api/schema";
import { pct } from "../lib/format";

type ColumnProfile = components["schemas"]["ColumnProfile"];

interface Props {
  column: ColumnProfile;
}

export function ColumnCard({ column: col }: Props): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const topK = col.top_k ?? [];
  const visibleTopK = expanded ? topK : topK.slice(0, 5);

  return (
    <section className="cc" aria-labelledby={`cc-${col.position}`}>
      <header className="cc__head">
        <h3 id={`cc-${col.position}`}>
          {col.name}
          {col.name !== col.safe_name && (
            <code className="cc__safe">→ {col.safe_name}</code>
          )}
        </h3>
        <div className="cc__badges">
          <TypeBadge column={col} />
          {col.pii_class !== "none" && <PiiBadge cls={col.pii_class} />}
          {col.pk_score >= 0.9 && <span className="cc__pk">PK candidate</span>}
          {col.truncated && <span className="cc__trunc">stats omitted</span>}
        </div>
      </header>

      <dl className="cc__stats">
        <Stat label="Nulls" value={`${col.null_count} (${pct(col.null_rate)})`} />
        {col.empty_string_count > 0 && (
          <Stat label="Empty strings" value={String(col.empty_string_count)} />
        )}
        <Stat
          label="Distinct"
          value={`${col.distinct_count} · ${col.cardinality_class}`}
        />
        {col.min != null && col.max != null && (
          <Stat label="Min / Max" value={`${col.min} … ${col.max}`} />
        )}
        {col.quantiles && (
          <Stat
            label="p1 / p50 / p99"
            value={`${col.quantiles.p1 ?? "—"} / ${col.quantiles.p50 ?? "—"} / ${col.quantiles.p99 ?? "—"}`}
          />
        )}
        {col.length_stats && (
          <Stat
            label="Length p50/p99"
            value={`${col.length_stats.p50} / ${col.length_stats.p99}`}
          />
        )}
      </dl>

      {(col.sample_values ?? []).length > 0 && (
        <>
          <h4>Samples</h4>
          <ul className="cc__samples">
            {(col.sample_values ?? []).map((v, i) => (
              <li key={i}>
                <code>{String(v)}</code>
              </li>
            ))}
          </ul>
        </>
      )}

      {visibleTopK.length > 0 && (
        <>
          <h4>Top values</h4>
          <ol className="cc__topk">
            {visibleTopK.map((t, i) => (
              <li key={i}>
                <code>{String(t.value)}</code>
                <span>{t.count}</span>
              </li>
            ))}
          </ol>
          {topK.length > 5 && (
            <button
              type="button"
              className="cc__more"
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? "Show top 5" : `Show all ${topK.length}`}
            </button>
          )}
        </>
      )}

      {col.date_format_candidates && (
        <p className="cc__patterns">
          Date formats:&nbsp;
          {Object.entries(col.date_format_candidates)
            .map(([fmt, rate]) => `${fmt} (${pct(rate)})`)
            .join(", ")}
        </p>
      )}

      {Object.keys(col.pattern_hits ?? {}).length > 0 && (
        <p className="cc__patterns">
          Patterns: {Object.keys(col.pattern_hits ?? {}).join(", ")}
        </p>
      )}

      {col.pii_warnings && col.pii_warnings.length > 0 && (
        <p className="cc__warn">May contain: {col.pii_warnings.join(", ")}</p>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="cc__stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TypeBadge({ column: col }: { column: ColumnProfile }): JSX.Element {
  const hints: string[] = [];
  if (col.leading_zero_ratio && col.leading_zero_ratio > 0) hints.push("leading 0");
  if (col.decimal_separator) {
    const sep =
      col.decimal_separator === "," ? "european" : col.thousands_separator ? "US" : "decimal";
    hints.push(sep);
  }
  if (col.currency_symbol) hints.push(`currency ${col.currency_symbol}`);
  if (col.percent_unit) hints.push("percent");
  return (
    <span className="cc__type">
      {col.inferred_type}
      {hints.length > 0 && <small>· {hints.join(" · ")}</small>}
    </span>
  );
}

function PiiBadge({ cls }: { cls: string }): JSX.Element {
  return <span className="cc__pii">PII: {cls}</span>;
}
