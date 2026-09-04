"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS: [string, string][] = [
  ["/", "Intelligence"],
  ["/events", "Events"],
  ["/discovery", "Discovery"],
  ["/lp", "LP Intelligence"],
  ["/talent", "Talent"],
  ["/network", "Network"],
  ["/models", "Models"],
  ["/data-quality", "Data Quality"],
  ["/weekly-runs", "Weekly Runs"],
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="nav">
      <h1>Chimera</h1>
      {LINKS.map(([href, label]) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href} className={active ? "active" : ""}>
            {label}
          </Link>
        );
      })}
      <div style={{ marginTop: 24, padding: "0 8px", fontSize: 11 }} className="faint">
        weekly batch · every recommendation explainable
      </div>
    </nav>
  );
}
