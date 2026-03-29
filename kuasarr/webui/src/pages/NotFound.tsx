import { useNavigate } from 'react-router-dom';
import { Home, ArrowLeft, AlertTriangle } from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <Layout>
      <div className="min-h-[60vh] flex items-center justify-center">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <div className="flex justify-center mb-6">
              <div className="p-4 bg-kuasarr-error/10 rounded-full">
                <AlertTriangle className="h-12 w-12 text-kuasarr-error" />
              </div>
            </div>
            <h1 className="text-4xl font-bold text-text-primary mb-2">404</h1>
            <h2 className="text-xl font-semibold text-text-primary mb-4">Page Not Found</h2>
            <p className="text-text-secondary mb-8">
              The page you are looking for does not exist or has been moved.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                variant="secondary"
                leftIcon={<ArrowLeft className="h-4 w-4" />}
                onClick={() => navigate(-1)}
              >
                Go Back
              </Button>
              <Button
                variant="primary"
                leftIcon={<Home className="h-4 w-4" />}
                onClick={() => navigate('/')}
              >
                Go Home
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
