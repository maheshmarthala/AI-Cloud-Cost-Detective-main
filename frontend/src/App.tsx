import { useEffect, useState } from 'react';
import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import Navbar from './components/Navbar';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Report from './pages/Report';
import { api } from './api';
function Protected() { return localStorage.getItem('token') ? <><Navbar/><main className="shell"><Outlet/></main></> : <Navigate to="/login" replace/>; }
export default function App() {
  const [mode, setMode] = useState('');
  useEffect(() => { api<{mode:string}>('/health').then(h => setMode(h.mode)).catch(() => setMode('offline')); }, []);
  return <>{mode === 'demo' && <div className="demo">DEMO MODE · Sample data only · No AWS resources are accessed</div>}
    {mode === 'offline' && <div className="demo">Backend unavailable. Check the API service.</div>}
    <Routes><Route path="/login" element={<Login/>}/><Route path="/signup" element={<Signup/>}/>
      <Route element={<Protected/>}><Route index element={<Dashboard/>}/><Route path="history" element={<History/>}/><Route path="reports/:id" element={<Report/>}/></Route>
      <Route path="*" element={<Navigate to="/" replace/>}/></Routes></>;
}
