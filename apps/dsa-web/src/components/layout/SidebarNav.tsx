import React, { useState } from 'react';
import { motion } from 'motion/react';
import {
  BarChart3,
  BriefcaseBusiness,
  FileText,
  Home,
  LogOut,
  MessageSquareQuote,
  Settings2,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onNavigate?: () => void;
};

type NavItem = {
  key: string;
  label: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: 'completion';
};

const LABELS = {
  home: '\u9996\u9875',
  chat: '\u95ee\u80a1',
  portfolio: '\u6301\u4ed3',
  backtest: '\u56de\u6d4b',
  marketReports: '\u5927\u76d8\u590d\u76d8\u62a5\u544a',
  settings: '\u8bbe\u7f6e',
  mainNav: '\u4e3b\u5bfc\u822a',
  chatBadge: '\u95ee\u80a1\u6709\u65b0\u6d88\u606f',
  logout: '\u9000\u51fa',
  logoutTitle: '\u9000\u51fa\u767b\u5f55',
  logoutMessage: '\u786e\u8ba4\u9000\u51fa\u5f53\u524d\u767b\u5f55\u72b6\u6001\u5417\uff1f\u9000\u51fa\u540e\u9700\u8981\u91cd\u65b0\u8f93\u5165\u5bc6\u7801\u3002',
  logoutConfirm: '\u786e\u8ba4\u9000\u51fa',
  cancel: '\u53d6\u6d88',
} as const;

const NAV_ITEMS: NavItem[] = [
  { key: 'home', label: LABELS.home, to: '/', icon: Home, exact: true },
  { key: 'chat', label: LABELS.chat, to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'portfolio', label: LABELS.portfolio, to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'backtest', label: LABELS.backtest, to: '/backtest', icon: BarChart3 },
  { key: 'market-reports', label: LABELS.marketReports, to: '/market-reports', icon: FileText },
  { key: 'settings', label: LABELS.settings, to: '/settings', icon: Settings2 },
];

export const SidebarNav: React.FC<SidebarNavProps> = ({ collapsed = false, onNavigate }) => {
  const { authEnabled, logout } = useAuth();
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <div className={cn('mb-4 flex items-center gap-2 px-1', collapsed ? 'justify-center' : '')}>
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-gradient text-[hsl(var(--primary-foreground))] shadow-[0_12px_28px_var(--nav-brand-shadow)]">
          <BarChart3 className="h-5 w-5" />
        </div>
        {!collapsed ? (
          <p className="min-w-0 truncate text-sm font-semibold text-foreground">DSA</p>
        ) : null}
      </div>

      <nav className="flex flex-1 flex-col gap-1.5" aria-label={LABELS.mainNav}>
        {NAV_ITEMS.map(({ key, label, to, icon: Icon, exact, badge }) => (
          <NavLink
            key={key}
            to={to}
            end={exact}
            onClick={onNavigate}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center gap-3 border-y border-x-0 text-sm transition-all',
                'h-[var(--nav-item-height)]',
                collapsed ? 'justify-center px-0' : 'px-[var(--nav-item-padding-x)]',
                isActive
                  ? 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-[hsl(var(--primary))]'
                  : 'border-transparent text-secondary-text hover:bg-[var(--nav-hover-bg)] hover:text-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive ? (
                  <motion.div
                    layoutId="activeIndicator"
                    className="absolute top-0 bottom-0 left-0 w-[var(--nav-indicator-width)] bg-[var(--nav-indicator-bg)] shadow-[0_0_10px_var(--nav-indicator-shadow)]"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2 }}
                  />
                ) : null}
                <Icon
                  className={cn(
                    'ml-1 h-5 w-5 shrink-0',
                    isActive ? 'text-[var(--nav-icon-active)]' : 'text-current',
                  )}
                />
                {!collapsed ? <span className="truncate">{label}</span> : null}
                {badge === 'completion' && completionBadge ? (
                  <StatusDot
                    tone="info"
                    data-testid="chat-completion-badge"
                    className={cn(
                      'absolute right-3 border-2 border-background shadow-[0_0_10px_var(--nav-indicator-shadow)]',
                      collapsed ? 'right-2 top-2' : '',
                    )}
                    aria-label={LABELS.chatBadge}
                  />
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-4 mb-2">
        <ThemeToggle variant="nav" collapsed={collapsed} />
      </div>

      {authEnabled ? (
        <button
          type="button"
          onClick={() => setShowLogoutConfirm(true)}
          className={cn(
            'mt-5 flex h-11 w-full cursor-pointer select-none items-center gap-3 rounded-2xl border border-transparent px-3 text-sm text-secondary-text transition-all hover:border-border/70 hover:bg-hover hover:text-foreground',
            collapsed ? 'justify-center px-2' : '',
          )}
          aria-label={LABELS.logout}
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed ? <span>{LABELS.logout}</span> : null}
        </button>
      ) : null}

      <ConfirmDialog
        isOpen={showLogoutConfirm}
        title={LABELS.logoutTitle}
        message={LABELS.logoutMessage}
        confirmText={LABELS.logoutConfirm}
        cancelText={LABELS.cancel}
        isDanger
        onConfirm={() => {
          setShowLogoutConfirm(false);
          onNavigate?.();
          void logout();
        }}
        onCancel={() => setShowLogoutConfirm(false)}
      />
    </div>
  );
};
