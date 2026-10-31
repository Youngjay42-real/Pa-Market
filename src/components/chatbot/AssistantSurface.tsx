'use client';

import { ChatWidget } from './ChatWidget';
import { MarketAssistant as DemoMarketAssistant } from './MarketAssistant';

/** Keep the existing contract-backed widget available without sending demo personas to Flask. */
export function AssistantSurface() {
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
  const explicitlyDisabled = process.env.NEXT_PUBLIC_CHATBOT_ENABLED === 'false';
  const hasBackend = Boolean(process.env.NEXT_PUBLIC_API_URL);
  const chatbotEnabled = !demoMode && !explicitlyDisabled && (
    process.env.NEXT_PUBLIC_CHATBOT_ENABLED === 'true' || hasBackend
  );

  return chatbotEnabled
    ? <ChatWidget />
    : <DemoMarketAssistant />;
}
