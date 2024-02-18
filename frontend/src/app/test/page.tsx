import ProtectedPage from '@/components/auth/ProtectedPage';

export default function TestPage() {
  return (
    <ProtectedPage>
      <div>
        <h1>Test Page</h1>
      </div>
    </ProtectedPage>
  );
}
