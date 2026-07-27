// Indian currency formatting + helpers
export function formatINR(amount) {
  if (amount == null || isNaN(amount)) return "—";
  const n = Number(amount);
  if (n >= 1_00_00_000) return `₹ ${(n / 1_00_00_000).toFixed(n % 1_00_00_000 === 0 ? 0 : 2)} Cr`;
  if (n >= 1_00_000) return `₹ ${(n / 1_00_000).toFixed(n % 1_00_000 === 0 ? 0 : 2)} L`;
  if (n >= 1_000) return `₹ ${(n / 1_000).toFixed(1)} K`;
  return `₹ ${n.toLocaleString("en-IN")}`;
}

export function formatINRFull(amount) {
  if (amount == null || isNaN(amount)) return "—";
  return `₹ ${Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function timeAgo(isoString) {
  if (!isoString) return "—";
  const d = new Date(isoString);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mo = Math.floor(day / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.floor(mo / 12)}y ago`;
}

export function fmtDate(isoString, withTime = false) {
  if (!isoString) return "—";
  const d = new Date(isoString);
  const opts = { day: "2-digit", month: "short", year: "numeric" };
  if (withTime) {
    opts.hour = "2-digit";
    opts.minute = "2-digit";
  }
  return d.toLocaleDateString("en-IN", opts);
}

export function initials(name) {
  if (!name) return "—";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}
