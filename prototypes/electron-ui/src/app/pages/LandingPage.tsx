import { useEffect } from 'react';
import { useNavigate } from 'react-router';

export default function LandingPage() {
  const navigate = useNavigate();

  useEffect(() => {
    // Redirect to the case viewer (which now includes patient browser)
    navigate('/case', { replace: true });
  }, [navigate]);

  return null;
}
