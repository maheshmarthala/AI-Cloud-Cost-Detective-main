import { NavLink, useNavigate } from 'react-router-dom';
export default function Navbar() {
  const navigate = useNavigate();
  return <header className="nav"><NavLink to="/" className="brand">◈ <span>Cost Detective</span></NavLink><nav aria-label="Main navigation"><NavLink to="/" end>Dashboard</NavLink><NavLink to="/history">History</NavLink><button className="quiet" onClick={() => { localStorage.removeItem('token'); navigate('/login'); }}>Sign out</button></nav></header>;
}
