"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/", label: "This week", cls: null as string | null },
  { href: "/people?class=FOUNDER", label: "Founders", cls: "FOUNDER" },
  { href: "/people?class=LP", label: "LPs", cls: "LP" },
  { href: "/people?class=TALENT", label: "Talent", cls: "TALENT" },
  { href: "/people?class=CONNECTOR", label: "Connectors", cls: "CONNECTOR" },
  { href: "/people", label: "Search everyone", cls: "" },
  { href: "/events", label: "Events", cls: null },
];

export default function Nav() {
  const pathname = usePathname();
  const activeClass = useSearchParams().get("class") || "";

  return (
    <nav className="nav">
      <Link href="/" className="brand">
        Chimera
      </Link>
      {LINKS.map((l) => {
        const onPeople = pathname === "/people";
        const active =
          l.href === "/"
            ? pathname === "/"
            : l.href.startsWith("/people")
              ? onPeople && (l.cls || "") === activeClass
              : pathname.startsWith(l.href);
        return (
          <Link key={l.href} href={l.href} className={active ? "active" : ""}>
            {l.label}
          </Link>
        );
      })}
      <div className="foot">Who to talk to, and why — every number traces back to a source.</div>
    </nav>
  );
}
