import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ColumnDef,
  SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { fetchStocks, screenStocks } from "./api/stocks";
import type { ApiStock, Criteria, Stock, StocksPayload } from "./types";

const DEFAULT_CRITERIA: Criteria = {
  includeValuation: true,
  businessMultiple: null,
  bookValueMultiple: null,
  minPrice: 15,
  maxPrice: 30,
  minVolume: 10_000,
  minReturn: null,
  minRevenue: null,
  minGrowth: null,
  minMargin: null,
  minEpsTarget: null,
  minCashflowTarget: null,
  minBookTarget: null,
  minBuySignals: null,
};

type ValuationPreferences = Partial<Pick<Criteria, "businessMultiple" | "bookValueMultiple">>;

function readValuationPreferences(): ValuationPreferences | null {
  try {
    const saved = JSON.parse(localStorage.getItem("noodle-valuation-v1") ?? "null") as Partial<ValuationPreferences> | null;
    if (!saved) return null;
    const preferences: ValuationPreferences = {};
    if (typeof saved.businessMultiple === "number" && saved.businessMultiple > 0) preferences.businessMultiple = saved.businessMultiple;
    if (typeof saved.bookValueMultiple === "number" && saved.bookValueMultiple > 0) preferences.bookValueMultiple = saved.bookValueMultiple;
    return Object.keys(preferences).length ? preferences : null;
  } catch {
    // Use provider defaults when browser storage is unavailable or malformed.
  }
  return null;
}

function initialCriteria(): Criteria {
  return { ...DEFAULT_CRITERIA, ...(readValuationPreferences() ?? {}) };
}

function saveValuationPreferences(preferences: ValuationPreferences | null) {
  try {
    if (preferences) localStorage.setItem("noodle-valuation-v1", JSON.stringify(preferences));
    else localStorage.removeItem("noodle-valuation-v1");
  } catch {
    // Recalculation still works when browser storage is unavailable.
  }
}

const NUMBER_FIELDS = [
  "close",
  "avg_volume_20",
  "return_20_pct",
  "high_52w",
  "revenue_fy",
  "revenue_growth_pct",
  "net_margin_pct",
  "eps_diluted",
  "operating_cashflow_fy",
  "operating_cashflow_per_share",
  "book_value_per_share",
  "business_multiple",
  "book_value_multiple",
  "eps_target_price",
  "cashflow_target_price",
  "book_value_target_price",
  "buy_signal_count",
] as const;

function numberOrNull(value: unknown): number | null {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeStock(raw: ApiStock): Stock {
  const normalized = { ...raw } as unknown as Stock;
  for (const field of NUMBER_FIELDS) normalized[field] = numberOrNull(raw[field]);
  normalized.distance_52w_pct =
    normalized.close !== null && normalized.high_52w !== null && normalized.high_52w > 0
      ? Math.round((normalized.close / normalized.high_52w - 1) * 10_000) / 100
      : null;
  return normalized;
}

function formatNumber(value: number | null, digits = 2): string {
  if (value === null) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function readWatchlist(): Set<string> {
  try {
    const saved = JSON.parse(localStorage.getItem("noodle-watch-v1") ?? "[]");
    return new Set(Array.isArray(saved) ? saved : []);
  } catch {
    return new Set();
  }
}

function passes(value: number | null, minimum: number | null): boolean {
  return minimum === null || (value !== null && value >= minimum);
}

function downloadCsv(rows: Stock[]) {
  const fields: (keyof Stock)[] = [
    "symbol", "name", "asof", "close", "avg_volume_20", "return_20_pct", "high_52w",
    "revenue_fy", "revenue_growth_pct", "net_margin_pct", "filing_date", "cik",
    "eps_diluted", "operating_cashflow_fy", "operating_cashflow_per_share",
    "book_value_per_share", "business_multiple", "book_value_multiple", "eps_target_price",
    "cashflow_target_price", "book_value_target_price", "eps_signal", "cashflow_signal",
    "book_value_signal", "buy_signal_count", "distance_52w_pct", "source",
  ];
  const quote = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [fields.join(","), ...rows.map((row) => fields.map((field) => quote(row[field])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "noodle_stock_candidates.csv";
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 5_000);
}

type NumberInputProps = {
  label: string;
  info: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
};

function NumberInput({ label, info, value, onChange, min, max, step = 0.1, placeholder = "Any" }: NumberInputProps) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        <span className="info-icon" role="img" tabIndex={0} aria-label={`${label}: ${info}`} title={info} data-tooltip={info}>i</span>
      </span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(event) => onChange(numberOrNull(event.target.value))}
      />
    </label>
  );
}

function TargetValue({ value, signal }: { value: number | null; signal: string }) {
  if (value === null) return <>—</>;
  return (
    <span className="target-value">
      ${formatNumber(value)}
      {signal === "BUY" && <small>Buy</small>}
    </span>
  );
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [draft, setDraft] = useState<Criteria>(initialCriteria);
  const [criteria, setCriteria] = useState<Criteria>(initialCriteria);
  const [valuationDefaults, setValuationDefaults] = useState({ businessMultiple: 15, bookValueMultiple: 1.5 });
  const [watchlist, setWatchlist] = useState<Set<string>>(readWatchlist);
  const [view, setView] = useState<"all" | "watchlist">("all");
  const [matchSearch, setMatchSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "avg_volume_20", desc: true }]);
  const [status, setStatus] = useState<"loading" | "ready" | "refreshing" | "stale" | "error">("loading");
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState("");
  const [completedAt, setCompletedAt] = useState<string | null>(null);
  const [providers, setProviders] = useState<StocksPayload["providers"]>();
  const dirty = JSON.stringify(draft) !== JSON.stringify(criteria);
  const draftNeedsSec = [
    draft.minRevenue, draft.minGrowth, draft.minMargin, draft.minEpsTarget,
    draft.minCashflowTarget, draft.minBookTarget, draft.minBuySignals,
  ].some((value) => value !== null) || draft.includeValuation;

  useEffect(() => {
    const controller = new AbortController();
    fetchStocks(controller.signal)
      .then((payload) => {
        setStocks(payload.stocks.map(normalizeStock));
        setDemo(payload.demo);
        if (payload.config) {
          const defaults = {
            businessMultiple: payload.config.business_multiple,
            bookValueMultiple: payload.config.book_value_multiple,
          };
          setValuationDefaults(defaults);
        }
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Could not load stock data.");
        setStatus("error");
      });
    return () => controller.abort();
  }, []);

  const activeBusinessMultiple = draft.businessMultiple ?? valuationDefaults.businessMultiple;
  const activeBookValueMultiple = draft.bookValueMultiple ?? valuationDefaults.bookValueMultiple;
  const valuedStocks = useMemo(() => stocks.map((stock) => {
    const epsTarget = stock.eps_diluted === null ? null : Math.round(stock.eps_diluted * activeBusinessMultiple * 100) / 100;
    const cashflowTarget = stock.operating_cashflow_per_share === null ? null : Math.round(stock.operating_cashflow_per_share * activeBusinessMultiple * 100) / 100;
    const bookTarget = stock.book_value_per_share === null ? null : Math.round(stock.book_value_per_share * activeBookValueMultiple * 100) / 100;
    const epsSignal = epsTarget !== null && stock.close !== null && epsTarget > stock.close ? "BUY" : "";
    const cashflowSignal = cashflowTarget !== null && stock.close !== null && cashflowTarget > stock.close ? "BUY" : "";
    const bookSignal = bookTarget !== null && stock.close !== null && bookTarget > stock.close ? "BUY" : "";
    const available = [epsTarget, cashflowTarget, bookTarget].some((value) => value !== null);
    return {
      ...stock,
      business_multiple: activeBusinessMultiple,
      book_value_multiple: activeBookValueMultiple,
      eps_target_price: epsTarget,
      cashflow_target_price: cashflowTarget,
      book_value_target_price: bookTarget,
      eps_signal: epsSignal,
      cashflow_signal: cashflowSignal,
      book_value_signal: bookSignal,
      buy_signal_count: available ? [epsSignal, cashflowSignal, bookSignal].filter(Boolean).length : null,
    };
  }), [activeBookValueMultiple, activeBusinessMultiple, stocks]);

  const filtered = useMemo(
    () => {
      const query = matchSearch.trim().toUpperCase();
      return valuedStocks.filter((stock) =>
        (view === "all" || watchlist.has(stock.symbol)) &&
        (!query || stock.symbol.toUpperCase().includes(query) || stock.name.toUpperCase().includes(query)) &&
        passes(stock.close, criteria.minPrice) &&
        (criteria.maxPrice === null || (stock.close !== null && stock.close <= criteria.maxPrice)) &&
        passes(stock.avg_volume_20, criteria.minVolume) &&
        passes(stock.return_20_pct, criteria.minReturn) &&
        passes(stock.revenue_fy, criteria.minRevenue) &&
        passes(stock.revenue_growth_pct, criteria.minGrowth) &&
        passes(stock.net_margin_pct, criteria.minMargin) &&
        passes(stock.eps_target_price, criteria.minEpsTarget) &&
        passes(stock.cashflow_target_price, criteria.minCashflowTarget) &&
        passes(stock.book_value_target_price, criteria.minBookTarget) &&
        passes(stock.buy_signal_count, criteria.minBuySignals));
    },
    [criteria, matchSearch, valuedStocks, view, watchlist],
  );

  const toggleWatchlist = (symbol: string) => {
    setWatchlist((current) => {
      const next = new Set(current);
      next.has(symbol) ? next.delete(symbol) : next.add(symbol);
      localStorage.setItem("noodle-watch-v1", JSON.stringify([...next]));
      return next;
    });
  };

  const columns = useMemo<ColumnDef<Stock>[]>(() => [
    {
      id: "watch", header: "Save", enableSorting: false,
      cell: ({ row }) => {
        const saved = watchlist.has(row.original.symbol);
        return (
          <button
            className="save-button"
            type="button"
            aria-label={`${saved ? "Remove" : "Add"} ${row.original.symbol} ${saved ? "from" : "to"} watchlist`}
            title={saved ? "Remove from watchlist" : "Add to watchlist"}
            onClick={() => toggleWatchlist(row.original.symbol)}
          >
            {saved ? "★" : "☆"}
          </button>
        );
      },
    },
    { accessorKey: "symbol", header: "Symbol" },
    { accessorKey: "name", header: "Company" },
    { accessorKey: "close", header: "Current price", cell: ({ getValue }) => `$${formatNumber(getValue<number | null>())}` },
    { accessorKey: "avg_volume_20", header: "20-day avg volume", cell: ({ getValue }) => formatNumber(getValue<number | null>(), 0) },
    { accessorKey: "eps_target_price", header: "EPS target", cell: ({ row }) => <TargetValue value={row.original.eps_target_price} signal={row.original.eps_signal} /> },
    { accessorKey: "cashflow_target_price", header: "OCF target", cell: ({ row }) => <TargetValue value={row.original.cashflow_target_price} signal={row.original.cashflow_signal} /> },
    { accessorKey: "book_value_target_price", header: "Book target", cell: ({ row }) => <TargetValue value={row.original.book_value_target_price} signal={row.original.book_value_signal} /> },
  ], [watchlist]);

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const latestDate = stocks.map((stock) => stock.asof).filter(Boolean).sort().at(-1) ?? "none";
  const financialCoverage = stocks.filter((stock) => stock.revenue_fy !== null).length;
  const incompletePrices = stocks.filter((stock) => stock.avg_volume_20 === null || stock.return_20_pct === null).length;
  const setCriterion = (key: keyof Criteria, value: number | null) => setDraft((current) => ({ ...current, [key]: value }));
  const setMultiple = (key: "businessMultiple" | "bookValueMultiple", value: number | null) => {
    setDraft((current) => {
      const next = { ...current, [key]: value };
      const preferences: ValuationPreferences = {};
      if (next.businessMultiple !== null && next.businessMultiple > 0) preferences.businessMultiple = next.businessMultiple;
      if (next.bookValueMultiple !== null && next.bookValueMultiple > 0) preferences.bookValueMultiple = next.bookValueMultiple;
      saveValuationPreferences(Object.keys(preferences).length ? preferences : null);
      return next;
    });
  };
  const resetMultiples = () => {
    saveValuationPreferences(null);
    setDraft((current) => ({ ...current, businessMultiple: null, bookValueMultiple: null }));
  };

  const applyFilters = async (event: FormEvent) => {
    event.preventDefault();
    setCriteria(draft);
    if (demo) return;
    setStatus("refreshing");
    setError("");
    try {
      const payload = await screenStocks(draft);
      setStocks(payload.stocks.map(normalizeStock));
      setDemo(payload.demo);
      setCompletedAt(payload.completed_at ?? null);
      setProviders(payload.providers);
      setStatus("ready");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not refresh provider data.");
      setStatus(stocks.length ? "stale" : "error");
    }
  };

  return (
    <main className="shell">
      <header className="masthead">
        <div className="brand-lockup">
          <div className="monogram" aria-hidden="true">NA</div>
          <div>
            <p className="eyebrow">Market intelligence console</p>
            <h1>Noodle Analytics</h1>
            <p className="intro">Screen market momentum against verified annual fundamentals.</p>
          </div>
        </div>
        <div className={`connection-panel ${status}`}>
          <div className="provider-row" aria-label="Connected data providers">
            <span><i /> Alpaca</span>
            <span><i /> SEC EDGAR</span>
          </div>
          <span className={`status-badge ${demo ? "demo" : ""} ${status}`}>
            {status === "loading" ? "Loading snapshot" : status === "refreshing" ? "Refreshing providers" : status === "stale" ? "Refresh failed" : status === "error" ? "Connection error" : demo ? "Synthetic demo" : "Provider data ready"}
          </span>
        </div>
      </header>

      <form className="filter-panel" onSubmit={applyFilters}>
        <div className="filter-heading">
          <div>
            <p className="section-label">Screener configuration</p>
            <h2>Set the signal thresholds</h2>
          </div>
          <div className="filter-actions">
            {status === "refreshing" ? <span className="pending">{draftNeedsSec ? "Screening Alpaca, then SEC survivors…" : "Screening Alpaca; SEC skipped…"}</span> : dirty && <span className="pending">Changes waiting to apply</span>}
            <button className="primary-button screen-button" type="submit" disabled={status === "refreshing"}>
              {status === "refreshing" ? "Refreshing…" : demo ? "Screen Demo" : "Refresh & Screen"}
            </button>
          </div>
        </div>
        <div className="filter-grid">
          <fieldset className="filter-group market-group">
            <legend>Alpaca market filters</legend>
            <div className="group-fields">
              <NumberInput label="Minimum price ($)" info="Uses the latest available Alpaca daily close, including the current session when available." value={draft.minPrice} min={0} step={0.01} onChange={(value) => setCriterion("minPrice", value)} />
              <NumberInput label="Maximum price ($)" info="Uses the latest available Alpaca daily close, including the current session when available." value={draft.maxPrice} min={0} step={0.01} onChange={(value) => setCriterion("maxPrice", value)} />
              <NumberInput label="Minimum average volume" info="Arithmetic mean of share volume across the latest 20 daily bars." value={draft.minVolume} min={0} step={10_000} onChange={(value) => setCriterion("minVolume", value)} />
              <NumberInput label="Minimum return (%)" info="Percentage price change across 20 trading sessions, calculated from 21 daily closes." value={draft.minReturn} onChange={(value) => setCriterion("minReturn", value)} />
            </div>
          </fieldset>
          <fieldset className="filter-group sec-group">
            <legend>SEC financial filters <span>{draftNeedsSec ? "enabled" : "optional"}</span></legend>
            <div className="group-fields">
              <NumberInput label="Minimum revenue ($m)" info="Latest compatible full-year revenue reported in a 10-K or 10-K/A, in USD millions." value={draft.minRevenue} min={0} step={1} onChange={(value) => setCriterion("minRevenue", value)} />
              <NumberInput label="Minimum growth (%)" info="Latest annual revenue compared with the nearest comparable prior full-year period." value={draft.minGrowth} onChange={(value) => setCriterion("minGrowth", value)} />
              <NumberInput label="Minimum net margin (%)" info="Annual net income divided by revenue for the same SEC reporting period." value={draft.minMargin} onChange={(value) => setCriterion("minMargin", value)} />
            </div>
          </fieldset>
          <fieldset className="filter-group valuation-group">
            <legend>
              Calculated valuation filters
              <label className="valuation-toggle">
                <input
                  type="checkbox"
                  checked={draft.includeValuation}
                  onChange={(event) => setDraft((current) => ({ ...current, includeValuation: event.target.checked }))}
                />
                Load valuation data
                <span className="info-icon" role="img" tabIndex={0} aria-label="Load valuation data: Queries SEC data for Alpaca survivors and calculates per-share targets." title="Queries SEC data for Alpaca survivors and calculates per-share targets." data-tooltip="Queries SEC data for Alpaca survivors and calculates per-share targets.">i</span>
              </label>
            </legend>
            <div className="group-fields">
              <NumberInput label="Business multiple" info="Multiplies diluted EPS and annual operating cash flow per share. Blank uses the configured default." value={draft.businessMultiple} min={0.1} step={0.1} placeholder={String(valuationDefaults.businessMultiple)} onChange={(value) => setMultiple("businessMultiple", value)} />
              <NumberInput label="Book-value multiple" info="Multiplies fiscal-year-end book value per common share. Blank uses the configured default." value={draft.bookValueMultiple} min={0.1} step={0.1} placeholder={String(valuationDefaults.bookValueMultiple)} onChange={(value) => setMultiple("bookValueMultiple", value)} />
              <NumberInput label="Minimum EPS target ($)" info="Diluted annual EPS multiplied by the active business multiple." value={draft.minEpsTarget} min={0} step={0.01} onChange={(value) => setCriterion("minEpsTarget", value)} />
              <NumberInput label="Minimum cash-flow target ($)" info="Annual operating cash flow per diluted weighted-average share multiplied by the business multiple." value={draft.minCashflowTarget} min={0} step={0.01} onChange={(value) => setCriterion("minCashflowTarget", value)} />
              <NumberInput label="Minimum book-value target ($)" info="Fiscal-year-end common equity per outstanding common share multiplied by the book-value multiple." value={draft.minBookTarget} min={0} step={0.01} onChange={(value) => setCriterion("minBookTarget", value)} />
              <NumberInput label="Minimum passing signals" info="Counts valuation targets above current price. Possible values range from zero through three." value={draft.minBuySignals} min={0} max={3} step={1} onChange={(value) => setCriterion("minBuySignals", value)} />
              <button className="secondary-button reset-multiples" type="button" onClick={resetMultiples}>Reset multiples</button>
            </div>
          </fieldset>
        </div>
      </form>

      <section className="results" aria-labelledby="results-title">
        <div className="results-heading">
          <div>
            <p className="section-label">Alpaca market data × SEC fundamentals</p>
            <h2 id="results-title">{filtered.length.toLocaleString()} matches</h2>
          </div>
          <div className="result-actions">
            <label className="match-search">
              <span className="sr-only">Search matches</span>
              <input
                type="search"
                value={matchSearch}
                placeholder="Search ticker or company"
                disabled={!stocks.length || status !== "ready"}
                onChange={(event) => setMatchSearch(event.target.value)}
              />
            </label>
            <div className="view-switcher" aria-label="Result view">
              <button type="button" className={view === "all" ? "active" : ""} onClick={() => setView("all")}>All stocks</button>
              <button type="button" className={view === "watchlist" ? "active" : ""} onClick={() => setView("watchlist")}>Watchlist <span>{watchlist.size}</span></button>
            </div>
            <button className="secondary-button" type="button" disabled={!filtered.length} onClick={() => downloadCsv(filtered)}>Export CSV</button>
          </div>
        </div>

        {(status === "error" || status === "stale") && (
          <div className="message error-message" role="alert">
            <strong>{status === "stale" ? "Fresh provider data could not be loaded. The prior snapshot remains below." : "Stock data could not be loaded."}</strong>
            <span>{error}</span>
          </div>
        )}
        {status !== "error" && (
          <>
            <div className="dataset-summary" aria-live="polite">
              <span><strong>{stocks.length.toLocaleString()}</strong> imported</span>
              <span><strong>{latestDate}</strong> latest price</span>
              <span><strong>{financialCoverage.toLocaleString()}</strong> with annual revenue</span>
              <span><strong>{incompletePrices.toLocaleString()}</strong> incomplete price histories</span>
              {completedAt && <span><strong>{new Date(completedAt).toLocaleTimeString()}</strong> provider refresh completed</span>}
              {providers && <span><strong>{providers.alpaca.candidates.toLocaleString()}</strong> passed Alpaca filters</span>}
              {providers && <span><strong>{providers.sec.checked ? `${providers.sec.candidates} checked` : "Skipped"}</strong> SEC stage</span>}
              {providers?.sec.checked && <span><strong>{providers.sec.facts_downloaded}</strong> SEC facts refreshed</span>}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <tr key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <th key={header.id}>
                          {header.isPlaceholder ? null : (
                            <button type="button" className="sort-button" disabled={!header.column.getCanSort()} onClick={header.column.getToggleSortingHandler()}>
                              {flexRender(header.column.columnDef.header, header.getContext())}
                              {{ asc: " ↑", desc: " ↓" }[header.column.getIsSorted() as string] ?? ""}
                            </button>
                          )}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id}>
                      {row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
                    </tr>
                  ))}
                  {!table.getRowModel().rows.length && status !== "loading" && (
                    <tr><td className="empty-state" colSpan={columns.length}>No stocks match the active criteria.</td></tr>
                  )}
                </tbody>
              </table>
              {status === "loading" && <div className="message">Loading the latest local snapshot…</div>}
            </div>
          </>
        )}
      </section>

      <footer>
        Missing values appear as — and never pass an active filter. Results support research; they are not trade recommendations.
      </footer>
    </main>
  );
}
