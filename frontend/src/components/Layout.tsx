import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import type { Role } from "../lib/types";

const LINKS: { to: string; label: string; roles: Role[] }[] = [
  { to: "/timetable", label: "Timetable", roles: ["student", "teacher"] },
  { to: "/todo", label: "To-Do", roles: ["student", "teacher"] },
  { to: "/documents", label: "Documents", roles: ["student", "teacher"] },
  { to: "/chat", label: "Tutor Chat", roles: ["student", "teacher"] },
  { to: "/examiner", label: "Examiner", roles: ["student"] },
  { to: "/parent", label: "Dashboard", roles: ["parent"] },
];

export default function Layout() {
  const { profile, signOut } = useAuth();
  if (!profile) return null;
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Study Assistant</span>
        <nav>
          {LINKS.filter((l) => l.roles.includes(profile.role)).map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="user">
          <span className="muted">
            {profile.full_name || profile.email} · {profile.role}
          </span>
          <button className="ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
