export type ApiStock = {
  symbol: string;
  name: string;
  asof: string;
  close: string | number | null;
  avg_volume_20: string | number | null;
  return_20_pct: string | number | null;
  high_52w: string | number | null;
  cik: string;
  revenue_fy: string | number | null;
  revenue_growth_pct: string | number | null;
  net_margin_pct: string | number | null;
  eps_diluted: string | number | null;
  operating_cashflow_fy: string | number | null;
  operating_cashflow_per_share: string | number | null;
  book_value_per_share: string | number | null;
  business_multiple: string | number | null;
  book_value_multiple: string | number | null;
  eps_target_price: string | number | null;
  cashflow_target_price: string | number | null;
  book_value_target_price: string | number | null;
  eps_signal: string;
  cashflow_signal: string;
  book_value_signal: string;
  buy_signal_count: string | number | null;
  filing_date: string;
  source: string;
};

export type Stock = Omit<
  ApiStock,
  | "close"
  | "avg_volume_20"
  | "return_20_pct"
  | "high_52w"
  | "revenue_fy"
  | "revenue_growth_pct"
  | "net_margin_pct"
  | "eps_diluted"
  | "operating_cashflow_fy"
  | "operating_cashflow_per_share"
  | "book_value_per_share"
  | "business_multiple"
  | "book_value_multiple"
  | "eps_target_price"
  | "cashflow_target_price"
  | "book_value_target_price"
  | "buy_signal_count"
> & {
  close: number | null;
  avg_volume_20: number | null;
  return_20_pct: number | null;
  high_52w: number | null;
  revenue_fy: number | null;
  revenue_growth_pct: number | null;
  net_margin_pct: number | null;
  eps_diluted: number | null;
  operating_cashflow_fy: number | null;
  operating_cashflow_per_share: number | null;
  book_value_per_share: number | null;
  business_multiple: number | null;
  book_value_multiple: number | null;
  eps_target_price: number | null;
  cashflow_target_price: number | null;
  book_value_target_price: number | null;
  buy_signal_count: number | null;
  distance_52w_pct: number | null;
};

export type Criteria = {
  includeValuation: boolean;
  businessMultiple: number | null;
  bookValueMultiple: number | null;
  minPrice: number | null;
  maxPrice: number | null;
  minVolume: number | null;
  minReturn: number | null;
  minRevenue: number | null;
  minGrowth: number | null;
  minMargin: number | null;
  minEpsTarget: number | null;
  minCashflowTarget: number | null;
  minBookTarget: number | null;
  minBuySignals: number | null;
};

export type StocksPayload = {
  demo: boolean;
  stocks: ApiStock[];
  refreshed?: boolean;
  completed_at?: string;
  config?: {
    business_multiple: number;
    book_value_multiple: number;
  };
  providers?: {
    alpaca: { checked: boolean; candidates: number; feed: string };
    sec: {
      checked: boolean;
      candidates: number;
      facts_downloaded: number;
      business_multiple: number;
      book_value_multiple: number;
    };
  };
};
