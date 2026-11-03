import { Navigate, Outlet, useLocation } from "react-router-dom";
import { HOME_BY_ROLE, useAuth } from "../lib/auth";
import type { Role } from "../lib/types";

/** Without `roles`: requires a signed-in user with a profile. With `roles`: also restricts by role. */
export default function RequireRole({ roles }: { roles?: Role[] }) {
  const { session, profile, loading, error, signOut } = useAuth();
  const location = useLocation();

  if (loading) return <div className="center muted">Loading…</div>;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!profile) {
    return (
      <div className="center">
        <div className="card">
          <p className="error">{error ?? "Your profile could not be loaded."}</p>
          <button onClick={signOut}>Sign out</button>
        </div>
      </div>
    );
  }
  if (roles && !roles.includes(profile.role)) return <Navigate to={HOME_BY_ROLE[profile.role]} replace />;
  return <Outlet />;
}
