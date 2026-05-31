import { useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error('404 Error: User attempted to access non-existent route:', location.pathname);
  }, [location.pathname]);

  return (
    <div className="auth-shell flex items-center justify-center p-6">
      <div className="card max-w-xl text-center">
        <div className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">Error</div>
        <h1 className="text-5xl font-extrabold text-foreground">404</h1>
        <p className="mt-3 text-base text-muted-foreground">The page you requested does not exist or may have been moved.</p>
        <Link to="/" className="mt-6 inline-flex rounded-lg bg-secondary px-5 py-3 text-sm font-semibold text-secondary-foreground hover:bg-secondary-hover">
          Return to Home
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
