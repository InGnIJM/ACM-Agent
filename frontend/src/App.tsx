import { Suspense, lazy } from "react";
import { Routes, Route, Navigate, Outlet } from "react-router-dom";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import useAuth from "./hooks/useAuth";
import AppLayout from "./components/layout/AppLayout";

// ---- public ----
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));

// ---- main ----
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Problems = lazy(() => import("./pages/Problems"));
const ProblemDetail = lazy(() => import("./pages/ProblemDetail"));
const Records = lazy(() => import("./pages/Records"));
const Profile = lazy(() => import("./pages/Profile"));
const Training = lazy(() => import("./pages/Training"));
const TrainingRecommend = lazy(() => import("./pages/TrainingRecommend"));
const Matching = lazy(() => import("./pages/Matching"));
const Teams = lazy(() => import("./pages/Teams"));
const TeamDetail = lazy(() => import("./pages/TeamDetail"));
const Ranking = lazy(() => import("./pages/Ranking"));
const Settings = lazy(() => import("./pages/Settings"));
const NotFound = lazy(() => import("./pages/NotFound"));

// ---- admin ----
const UserManagement = lazy(() => import("./pages/admin/UserManagement"));
const UserDetail = lazy(() => import("./pages/admin/UserDetail"));
const BotConfig = lazy(() => import("./pages/admin/BotConfig"));
const CrawlerManagement = lazy(() => import("./pages/admin/CrawlerManagement"));

function Loading() {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
      <CircularProgress />
    </Box>
  );
}

/** Redirect to /login if not authenticated */
function RequireAuth() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <Loading />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Main layout: sidebar + topbar + content */
function MainLayout() {
  return (
    <AppLayout>
      <Suspense fallback={<Loading />}>
        <Outlet />
      </Suspense>
    </AppLayout>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Authenticated + Layout */}
        <Route element={<RequireAuth />}>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/problems" element={<Problems />} />
            <Route path="/problems/:id" element={<ProblemDetail />} />
            <Route path="/records" element={<Records />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/training" element={<Training />} />
            <Route path="/training/recommend" element={<TrainingRecommend />} />
            <Route path="/matching" element={<Matching />} />
            <Route path="/teams" element={<Teams />} />
            <Route path="/teams/:id" element={<TeamDetail />} />
            <Route path="/ranking" element={<Ranking />} />
            <Route path="/settings" element={<Settings />} />

            {/* Admin */}
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/users/:id" element={<UserDetail />} />
            <Route path="/admin/bot" element={<BotConfig />} />
            <Route path="/admin/crawler" element={<CrawlerManagement />} />
          </Route>
        </Route>

        {/* 404 */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
