'use client';

import { useAuth } from '@/context/AuthContext';
import { useRouter } from 'next/navigation';

export default function ProtectedPage({ children }: any) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();

  console.log({ isAuthenticated });

  if (!isAuthenticated && !loading) {
    router.push('/');
  }

  if (loading) {
    return <div>Loading...</div>;
  }

  if (isAuthenticated) {
    return children;
  }

  router.push('/');
}
