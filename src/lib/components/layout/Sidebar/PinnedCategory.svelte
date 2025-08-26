<script lang="ts">
import { createEventDispatcher } from 'svelte';
import { chatId, mobile, showSidebar, models } from '$lib/stores';
import PinnedModelItem from './PinnedModelItem.svelte';
import Folder from '../../common/Folder.svelte';
import PinnedCategory from './PinnedCategory.svelte';

const dispatch = createEventDispatcher();

export let category: { name: string; children: any[] };
export let shiftKey = false;

const handleUnpin = (id: string) => {
  dispatch('unpinModel', id);
};
</script>

<Folder name={category.name} className="px-1.5 mt-0.5" dragAndDrop={false}>
  {#each category.children as item (typeof item === 'string' ? item : item.name)}
    {#if typeof item === 'string'}
      {@const model = $models.find((m) => m.id === item)}
      {#if model}
        <PinnedModelItem
          {model}
          {shiftKey}
          onClick={() => {
            chatId.set('');
            if ($mobile) {
              showSidebar.set(false);
            }
          }}
          onUnpin={() => handleUnpin(item)}
        />
      {/if}
    {:else}
      <PinnedCategory category={item} {shiftKey} on:unpinModel={(e) => handleUnpin(e.detail)} />
    {/if}
  {/each}
</Folder>
