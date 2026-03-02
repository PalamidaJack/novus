import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Send, Sparkles, Bot, User, Loader2, Settings2, ChevronUp, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Slider } from '../components/ui/Slider';
import { api } from '../utils/api';
import { cn } from '../utils/cn';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  metadata?: {
    agents_used?: number;
    confidence?: number;
    reasoning?: string;
  };
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello! I\'m NOVUS, your autonomous agentic AI platform. I can help you with research, coding, analysis, and complex problem-solving using my swarm of specialized agents. What would you like to work on?',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [numAgents, setNumAgents] = useState(3);
  const [consensusThreshold, setConsensusThreshold] = useState(0.75);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: llmConfig } = useQuery({
    queryKey: ['llm-config'],
    queryFn: () => api.get('/config/llm').then((r) => r.data),
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await api.post('/swarm/solve', {
        problem: input,
        num_agents: numAgents,
        consensus_threshold: consensusThreshold,
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.data.solution,
        timestamp: new Date(),
        metadata: {
          agents_used: response.data.agents_used,
          confidence: response.data.confidence,
        },
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const suggestions = [
    'Research the latest developments in quantum computing',
    'Help me design a novel energy storage solution',
    'Analyze the pros and cons of different LLM architectures',
    'Create a plan for learning machine learning from scratch',
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Chat with NOVUS</h1>
          <p className="mt-2 text-gray-400">
            Interact with the swarm using natural language
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowConfig(!showConfig)}
          className="flex items-center gap-2 text-gray-400"
        >
          <Settings2 className="h-4 w-4" />
          Config
          {showConfig ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </Button>
      </div>

      {/* Collapsible Config Panel */}
      <AnimatePresence>
        {showConfig && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden mb-4"
          >
            <Card>
              <CardContent className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <Slider
                    label="Agent Count"
                    value={numAgents}
                    onChange={setNumAgents}
                    min={1}
                    max={20}
                  />
                  <Slider
                    label="Consensus Threshold"
                    value={consensusThreshold}
                    onChange={setConsensusThreshold}
                    min={0}
                    max={1}
                    step={0.05}
                  />
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-300">Active Model</label>
                    <p className="text-sm text-emerald-400 font-mono">
                      {llmConfig?.model || llmConfig?.provider || 'Not configured'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-4">
        <AnimatePresence initial={false}>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className={cn(
                'flex gap-4',
                message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
              )}
            >
              <div
                className={cn(
                  'flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center',
                  message.role === 'user'
                    ? 'bg-emerald-500'
                    : 'bg-gradient-to-br from-emerald-500 to-teal-600'
                )}
              >
                {message.role === 'user' ? (
                  <User className="h-5 w-5 text-white" />
                ) : (
                  <Bot className="h-5 w-5 text-white" />
                )}
              </div>
              <div
                className={cn(
                  'max-w-3xl rounded-2xl px-6 py-4',
                  message.role === 'user'
                    ? 'bg-emerald-500 text-white'
                    : 'bg-gray-800 text-gray-100'
                )}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>

                {message.metadata && (
                  <div className="mt-3 pt-3 border-t border-gray-700/50 flex items-center gap-4 text-xs">
                    {message.metadata.agents_used && (
                      <span className="flex items-center gap-1 text-gray-400">
                        <Sparkles className="h-3 w-3" />
                        {message.metadata.agents_used} agents
                      </span>
                    )}
                    {message.metadata.confidence && (
                      <span className="text-gray-400">
                        Confidence: {(message.metadata.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                )}

                <span
                  className={cn(
                    'block mt-2 text-xs',
                    message.role === 'user' ? 'text-emerald-100' : 'text-gray-500'
                  )}
                >
                  {message.timestamp.toLocaleTimeString()}
                </span>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-3 text-gray-400"
          >
            <div className="flex space-x-1">
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-sm">Swarm is thinking...</span>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="mt-6 pt-6 border-t border-gray-800">
        {/* Suggestions */}
        {messages.length < 3 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => setInput(suggestion)}
                className="px-4 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-full transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-4">
          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask NOVUS anything..."
              className="w-full px-6 py-4 bg-gray-800 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all"
              disabled={isLoading}
            />
          </div>
          <Button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-6 py-4 bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
