'use client';

import { ChatWidget } from './ChatWidget';
import { MarketAssistant as DemoMarketAssistant } from './MarketAssistant';

/** Keep the existing contract-backed widget available without sending demo personas to Flask. */
export function AssistantSurface() {
  return process.env.NEXT_PUBLIC_CHATBOT_ENABLED === 'true'
    ? <ChatWidget />
    : <DemoMarketAssistant />;
}
