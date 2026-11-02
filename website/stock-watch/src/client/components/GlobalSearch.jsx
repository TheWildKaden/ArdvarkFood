import { useEffect, useRef } from "react";
import { Search, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import SearchBox from "./SearchBox.jsx";

export default function GlobalSearch({ onClose }) {
  const dialog = useRef(null);
  const navigate = useNavigate();
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  return <dialog className="search-dialog" ref={dialog} onClose={onClose} onClick={(event) => { if (event.target === dialog.current) onClose(); }}>
    <div className="global-search-header"><Search size={17} /><SearchBox placeholder="Search stocks, companies…" onSelect={(stock) => { navigate(`/stock/${encodeURIComponent(stock.symbol)}`); onClose(); }} /><button className="icon-button" onClick={onClose} aria-label="Close search"><X size={17} /></button></div>
    <div className="global-search-hint">Search company names or tickers. Select a result to open its market detail.</div>
  </dialog>;
}
