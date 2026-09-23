import { useState } from 'react';
import PropTypes from 'prop-types';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useMediaQuery } from 'react-responsive';
import AppBar from '@mui/material/AppBar';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import AddCircleOutlinedIcon from '@mui/icons-material/AddCircleOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import ListAltOutlinedIcon from '@mui/icons-material/ListAltOutlined';
import LogoutIcon from '@mui/icons-material/Logout';
import MenuIcon from '@mui/icons-material/Menu';
import useAuth from '../hooks/useAuth';
import { ROLE_LABELS } from '../constants';
import ErrorBoundary from './ErrorBoundary';

const DRAWER_WIDTH = 240;

/** Navigation entries; `roles` limits who sees an entry. */
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: <DashboardOutlinedIcon />, end: true },
  { to: '/incidents', label: 'Incidents', icon: <ListAltOutlinedIcon />, end: true },
  { to: '/incidents/new', label: 'Report incident', icon: <AddCircleOutlinedIcon /> },
];

/**
 * Side navigation, filtered to the user's role.
 * @param {{role: string, onNavigate?: function}} props
 * @returns {JSX.Element}
 */
function NavList({ role, onNavigate }) {
  return (
    <List component="nav" aria-label="Main navigation">
      {NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role)).map((item) => (
        <ListItemButton
          key={item.to}
          component={NavLink}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          sx={{ mx: 1, borderRadius: 1, '&.active': { bgcolor: 'action.selected', fontWeight: 600 } }}
        >
          <ListItemIcon sx={{ minWidth: 40 }}>{item.icon}</ListItemIcon>
          <ListItemText primary={item.label} />
        </ListItemButton>
      ))}
    </List>
  );
}

NavList.propTypes = {
  role: PropTypes.string.isRequired,
  onNavigate: PropTypes.func,
};

/**
 * App shell: top bar with the user and logout, and a navigation drawer that is
 * permanent on desktop and a hamburger menu on mobile.
 * @returns {JSX.Element}
 */
export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const isMobile = useMediaQuery({ maxWidth: 899 });
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const drawer = (
    <>
      <Toolbar />
      <NavList role={user.role} onNavigate={isMobile ? () => setDrawerOpen(false) : undefined} />
    </>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <Toolbar>
          {isMobile && (
            <IconButton color="inherit" edge="start" aria-label="Open menu" onClick={() => setDrawerOpen(true)} sx={{ mr: 1 }}>
              <MenuIcon />
            </IconButton>
          )}
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }} noWrap>
            ACME Incidents
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main', fontSize: 14 }} aria-hidden>
              {user.name.split(' ').map((part) => part[0]).join('').slice(0, 2)}
            </Avatar>
            {!isMobile && (
              <Box sx={{ lineHeight: 1.2 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{user.name}</Typography>
                <Typography variant="caption" sx={{ opacity: 0.8 }}>{ROLE_LABELS[user.role]}</Typography>
              </Box>
            )}
            <Divider orientation="vertical" flexItem sx={{ borderColor: 'rgba(255,255,255,0.3)', mx: 0.5 }} />
            {isMobile ? (
              <IconButton color="inherit" aria-label="Log out" onClick={handleLogout}><LogoutIcon /></IconButton>
            ) : (
              <Button color="inherit" startIcon={<LogoutIcon />} onClick={handleLogout}>Log out</Button>
            )}
          </Box>
        </Toolbar>
      </AppBar>

      <Drawer
        variant={isMobile ? 'temporary' : 'permanent'}
        open={isMobile ? drawerOpen : true}
        onClose={() => setDrawerOpen(false)}
        sx={{
          width: isMobile ? undefined : DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
      >
        {drawer}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 3 } }}>
        <Toolbar />
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Box>
    </Box>
  );
}
