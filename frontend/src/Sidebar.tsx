const destinations = [
  { label: "Screener", icon: "M4 4h16l-6 7v7l-4 2v-9Z" },
  { label: "Holdings", icon: "M4 8h16v12H4ZM9 8V4h6v4M4 13h16" },
  { label: "Trading History", icon: "M4 5v5h5M4 10a8 8 0 1 1 0 5M12 7v5l3 2" },
  { label: "Performance", icon: "M4 4v16h16M7 15l4-5 4 2 5-7" },
  { label: "Analysis", icon: "M5 20V10h3v10M11 20V4h3v16M17 20v-7h3v7" },
  { label: "Imports", icon: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" },
  { label: "Settings", icon: "M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6" },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <a className="sidebar-brand" href="#screener" aria-label="Market Nuance home">
        <span className="sidebar-monogram" aria-hidden="true">MN</span>
        <span>Market Nuance<small>Investment workspace</small></span>
      </a>
      <nav aria-label="Main navigation">
        <p className="section-label sidebar-label">Workspace</p>
        <ul className="nav-list">
          {destinations.map(({ label, icon }, index) => (
            <li key={label}>
              {index === 0 ? (
                <a className="nav-item active" href="#screener" aria-current="page">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d={icon} /></svg>
                  <span>{label}</span><span className="nav-current" aria-hidden="true" />
                </a>
              ) : (
                <button className="nav-item" type="button" disabled title={`${label} — coming soon`}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d={icon} /></svg>
                  <span>{label}</span><span className="sr-only"> — coming soon</span>
                </button>
              )}
            </li>
          ))}
        </ul>
        <p className="nav-hint">More pages coming soon</p>
      </nav>
      <div className="sidebar-note">
        <p className="section-label">Your investing picture</p>
        <p>Discover opportunities today. Holdings, trade history, and portfolio insights are next.</p>
      </div>
    </aside>
  );
}
