export {};
declare module 'vue' { export interface GlobalComponents {
  UiInput: typeof import('../components/ui/controls')['UiInput'];
  UiSelect: typeof import('../components/ui/controls')['UiSelect'];
} }
