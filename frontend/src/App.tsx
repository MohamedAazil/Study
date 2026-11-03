import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireRole from "./components/RequireRole";
import { HOME_BY_ROLE, useAuth } from "./lib/auth";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";
import ExaminerPage from "./pages/ExaminerPage";
import LoginPage from "./pages/LoginPage";
import ParentDashboardPage from "./pages/ParentDashboardPage";
import TimetablePage from "./pages/TimetablePage";
import TodoPage from "./pages/TodoPage";

function Home() {
  const { profile } = useAuth();
  return <Navigate to={profile ? HOME_BY_ROLE[profile.role] : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireRole />}>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route element={<RequireRole roles={["student", "teacher"]} />}>
            <Route path="/timetable" element={<TimetablePage />} />
            <Route path="/todo" element={<TodoPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Route>
          <Route element={<RequireRole roles={["student"]} />}>
            <Route path="/examiner" element={<ExaminerPage />} />
          </Route>
          <Route element={<RequireRole roles={["parent"]} />}>
            <Route path="/parent" element={<ParentDashboardPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
