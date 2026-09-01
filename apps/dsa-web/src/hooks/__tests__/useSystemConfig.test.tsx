import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSystemConfig } from '../useSystemConfig';

const { getConfig, validate, update } = vi.hoisted(() => ({
  getConfig: vi.fn(),
  validate: vi.fn(),
  update: vi.fn(),
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig,
    validate,
    update,
  },
  SystemConfigConflictError: class extends Error {},
  SystemConfigValidationError: class extends Error {
    issues: unknown[] = [];
    parsedError = {
      title: 'validation error',
      message: 'validation error',
      rawMessage: 'validation error',
      category: 'http_error',
    };
  },
}));

const sampleConfig = {
  configVersion: 'v1',
  maskToken: '******',
  items: [
    {
      key: 'STOCK_LIST',
      value: 'SH600000',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'STOCK_LIST',
        category: 'base',
        dataType: 'string',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    },
  ],
};

const screenerDefaultsConfig = {
  configVersion: 'v1',
  maskToken: '******',
  items: [
    {
      key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE',
      value: 'standard',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE',
        category: 'system',
        dataType: 'string',
        uiControl: 'select',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: ['standard', 'aggressive'],
        validation: {},
        displayOrder: 59,
      },
    },
    {
      key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N',
      value: '30',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N',
        category: 'system',
        dataType: 'integer',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 60,
      },
    },
    {
      key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT',
      value: '4',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT',
        category: 'system',
        dataType: 'number',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 61,
      },
    },
    {
      key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI',
      value: '2',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI',
        category: 'system',
        dataType: 'number',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 62,
      },
    },
    {
      key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER',
      value: '2',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER',
        category: 'system',
        dataType: 'number',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 63,
      },
    },
  ],
};

describe('useSystemConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getConfig.mockResolvedValue(sampleConfig);
    validate.mockResolvedValue({ valid: true, issues: [] });
    update.mockResolvedValue({ warnings: [] });
  });

  it('keeps load callback stable after a successful load', async () => {
    const { result } = renderHook(() => useSystemConfig());
    const firstLoad = result.current.load;

    await act(async () => {
      await result.current.load();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(result.current.load).toBe(firstLoad);
  });

  it('saves momentum screener default fields through system config update flow', async () => {
    getConfig
      .mockResolvedValueOnce(screenerDefaultsConfig)
      .mockResolvedValueOnce({
        ...screenerDefaultsConfig,
        configVersion: 'v2',
        items: [
          { ...screenerDefaultsConfig.items[0], value: 'aggressive' },
          { ...screenerDefaultsConfig.items[1], value: '12' },
          { ...screenerDefaultsConfig.items[2], value: '8.5' },
          { ...screenerDefaultsConfig.items[3], value: '4.5' },
          { ...screenerDefaultsConfig.items[4], value: '6' },
        ],
      });

    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    act(() => {
      result.current.setDraftValue('MOMENTUM_SCREENER_DEFAULT_PROFILE', 'aggressive');
      result.current.setDraftValue('MOMENTUM_SCREENER_DEFAULT_TOP_N', '12');
      result.current.setDraftValue('MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT', '8.5');
      result.current.setDraftValue('MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI', '4.5');
      result.current.setDraftValue('MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER', '6');
    });

    await act(async () => {
      await result.current.save();
    });

    expect(validate).toHaveBeenCalledWith({
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'aggressive' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '12' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT', value: '8.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI', value: '4.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER', value: '6' },
      ],
    });

    expect(update).toHaveBeenCalledWith({
      configVersion: 'v1',
      maskToken: '******',
      reloadNow: true,
      items: [
        { key: 'MOMENTUM_SCREENER_DEFAULT_PROFILE', value: 'aggressive' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_TOP_N', value: '12' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_CHANGE_PCT', value: '8.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_AMOUNT_YI', value: '4.5' },
        { key: 'MOMENTUM_SCREENER_DEFAULT_MIN_TURNOVER', value: '6' },
      ],
    });
  });
});
