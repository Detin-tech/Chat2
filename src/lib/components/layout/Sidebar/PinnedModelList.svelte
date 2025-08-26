<script lang="ts">
import Sortable from 'sortablejs';
import { onMount } from 'svelte';

import { chatId, mobile, models, settings, showSidebar } from '$lib/stores';
import { updateUserSettings } from '$lib/apis/users';
import PinnedModelItem from './PinnedModelItem.svelte';
import PinnedCategory from './PinnedCategory.svelte';
import { removeModelFromTree } from '$lib/utils/pinned-models';

export let selectedChatId = null;
export let shiftKey = false;

const unpinModel = async (modelId: string) => {
  const tree = removeModelFromTree($settings.pinnedModels ?? [], modelId);
  settings.set({ ...$settings, pinnedModels: tree });
  await updateUserSettings(localStorage.token, { ui: $settings });
};

const initPinnedModelsSortable = () => {
  const pinnedModelsList = document.getElementById('pinned-models-list');
  if (pinnedModelsList && !$mobile) {
    new Sortable(pinnedModelsList, {
      animation: 150,
      onUpdate: async (event) => {
        const pinned = $settings.pinnedModels;
        const moved = pinned.splice(event.oldIndex, 1)[0];
        pinned.splice(event.newIndex, 0, moved);
        settings.set({ ...$settings, pinnedModels: pinned });
        await updateUserSettings(localStorage.token, { ui: $settings });
      }
    });
  }
};

onMount(() => {
  initPinnedModelsSortable();
});
</script>

<div class="mt-0.5 pb-1.5" id="pinned-models-list">
  {#each $settings.pinnedModels as item (typeof item === 'string' ? item : item.name)}
    {#if typeof item === 'string'}
      {@const model = $models.find((model) => model.id === item)}
      {#if model}
        <PinnedModelItem
          {model}
          {shiftKey}
          onClick={() => {
            selectedChatId = null;
            chatId.set('');
            if ($mobile) {
              showSidebar.set(false);
            }
          }}
          onUnpin={() => unpinModel(item)}
        />
      {/if}
    {:else}
      <PinnedCategory category={item} {shiftKey} on:unpinModel={(e) => unpinModel(e.detail)} />
    {/if}
  {/each}
</div>
