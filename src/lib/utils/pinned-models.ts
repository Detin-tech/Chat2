export type PinnedItem = string | PinnedCategory;
export interface PinnedCategory {
  name: string;
  children: PinnedItem[];
}

export const getPinnedModelIds = (items: PinnedItem[] = []): string[] => {
  const ids: string[] = [];
  for (const item of items) {
    if (typeof item === 'string') {
      ids.push(item);
    } else if (item?.children) {
      ids.push(...getPinnedModelIds(item.children));
    }
  }
  return ids;
};

export const removeModelFromTree = (items: PinnedItem[] = [], modelId: string): PinnedItem[] => {
  const result: PinnedItem[] = [];
  for (const item of items) {
    if (typeof item === 'string') {
      if (item !== modelId) result.push(item);
    } else {
      const children = removeModelFromTree(item.children ?? [], modelId);
      if (children.length > 0) {
        result.push({ ...item, children });
      }
    }
  }
  return result;
};

export const addModelToTree = (items: PinnedItem[] = [], modelId: string): PinnedItem[] => {
  return [...items, modelId];
};
