import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Alert, AlertDescription } from './ui/alert';
import { Loader2, CreditCard, CheckCircle2 } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001/api';

const SubscribeToJournalist = ({ journalistId, journalistName, onSubscribed }) => {
  const auth = useAuth();
  const [price, setPrice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscribing, setSubscribing] = useState(false);
  const [subscribed, setSubscribed] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJournalistPrice();
    checkSubscriptionStatus();
  }, [journalistId]);

  const fetchJournalistPrice = async () => {
    try {
      // Fetch journalist's price
      const response = await fetch(`${API_BASE_URL}/stripe/journalist/my-price?journalist_id=${journalistId}`, {
        headers: auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}
      });

      if (response.ok) {
        const data = await response.json();
        if (data.has_price) {
          setPrice(data.plan);
        }
      }
    } catch (err) {
      console.error('Error fetching price:', err);
    } finally {
      setLoading(false);
    }
  };

  const checkSubscriptionStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stripe/my-subscriptions`, {
        headers: auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}
      });

      if (response.ok) {
        const data = await response.json();
        const isSubscribed = data.subscriptions?.some(
          sub => sub.journalist_user_id === journalistId && sub.status === 'active'
        );
        setSubscribed(isSubscribed);
      }
    } catch (err) {
      console.error('Error checking subscription:', err);
    }
  };

  const handleSubscribe = async () => {
    if (!auth?.token) {
      setError('Please log in to subscribe');
      return;
    }

    try {
      setSubscribing(true);
      setError(null);

      const response = await fetch(`${API_BASE_URL}/stripe/subscribe/${journalistId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${auth.token}`
        },
        body: JSON.stringify({
          success_url: `${window.location.origin}/settings?success=paid`,
          cancel_url: window.location.href
        })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to create checkout session');
      }

      const data = await response.json();
      // Redirect to Stripe Checkout
      window.location.href = data.checkout_url;
    } catch (err) {
      setError(err.message);
      setSubscribing(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center p-6">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (!price) {
    return (
      <Card>
        <CardContent className="p-6">
          <Alert>
            <AlertDescription>
              This journalist hasn't set up paid subscriptions yet.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (subscribed) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-6 w-6 text-green-500" />
            <div>
              <p className="font-medium">You're subscribed!</p>
              <p className="text-sm text-muted-foreground">
                Thank you for supporting {journalistName}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subscribe to {journalistName}</CardTitle>
        <CardDescription>
          Get exclusive access to premium content
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="bg-muted p-4 rounded-lg">
          <div className="text-3xl font-bold mb-1">
            {price.price_display}
            <span className="text-base font-normal text-muted-foreground">/month</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Billed monthly • Cancel anytime
          </p>
        </div>

        <div className="space-y-2 text-sm">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
            <span>Exclusive commentary and insights</span>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
            <span>Early access to content</span>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
            <span>Support independent journalism</span>
          </div>
        </div>

        <Button 
          onClick={handleSubscribe} 
          disabled={subscribing || !auth?.token}
          className="w-full"
          size="lg"
        >
          {subscribing ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading...
            </>
          ) : (
            <>
              <CreditCard className="mr-2 h-4 w-4" />
              Subscribe Now
            </>
          )}
        </Button>

        {!auth?.token && (
          <p className="text-xs text-center text-muted-foreground">
            Please log in to subscribe
          </p>
        )}
      </CardContent>
    </Card>
  );
};

export default SubscribeToJournalist;
