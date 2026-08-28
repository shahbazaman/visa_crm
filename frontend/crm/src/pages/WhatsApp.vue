<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-gray-2">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-2 px-1 py-1 text-lg font-medium text-ink-gray-7">
            <WhatsAppIcon class="size-5 text-[#25D366]" />
            <span>{{ __('WhatsApp') }}</span>
          </div>
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span class="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            {{ __('In-App Browser') }}
          </span>
        </div>
      </template>
      <template #right-header>
        <Button
          :label="__('Reload')"
          iconLeft="refresh-cw"
          variant="outline"
          size="sm"
          @click="reloadFrame"
        />
        <Button
          :label="__('App Window')"
          iconLeft="external-link"
          variant="outline"
          size="sm"
          @click="openPopoutWindow"
        />
        <Button
          :label="__('Open in Tab')"
          iconLeft="arrow-up-right"
          variant="solid"
          size="sm"
          @click="openNewTab"
        />
      </template>
    </LayoutHeader>

    <!-- In-built Browser Shell -->
    <div class="flex flex-col flex-1 p-2 sm:p-3 overflow-hidden">
      <div class="flex flex-col flex-1 rounded-lg border border-surface-gray-3 bg-surface-white shadow-sm overflow-hidden">
        
        <!-- Browser Navigation Toolbar -->
        <div class="flex items-center justify-between px-3 py-2 bg-surface-gray-2 border-b border-surface-gray-3 gap-2">
          <div class="flex items-center gap-1.5">
            <button
              class="p-1 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Reload Frame"
              @click="reloadFrame"
            >
              <FeatherIcon name="rotate-cw" class="size-3.5" />
            </button>
            <button
              class="p-1 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Reset URL"
              @click="resetUrl"
            >
              <FeatherIcon name="home" class="size-3.5" />
            </button>
          </div>

          <!-- Browser Address Bar -->
          <div class="flex-1 max-w-xl flex items-center gap-2 px-3 py-1 bg-surface-white rounded border border-surface-gray-3 shadow-inner text-xs text-ink-gray-7">
            <FeatherIcon name="lock" class="size-3 text-emerald-600 flex-shrink-0" />
            <span class="truncate select-all font-mono text-ink-gray-8">{{ currentUrl }}</span>
          </div>

          <div class="flex items-center gap-1.5">
            <button
              class="p-1 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Toggle Fullscreen"
              @click="toggleFullscreen"
            >
              <FeatherIcon :name="isFullscreen ? 'minimize-2' : 'maximize-2'" class="size-3.5" />
            </button>
          </div>
        </div>

        <!-- Frame View Area -->
        <div class="relative flex-1 w-full h-full bg-surface-gray-1 overflow-hidden" ref="browserContainer">
          <iframe
            v-if="frameKey"
            :key="frameKey"
            id="whatsapp-embedded-frame"
            :src="currentUrl"
            class="w-full h-full border-0"
            allow="camera; microphone; clipboard-read; clipboard-write; notifications; display-capture"
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals allow-downloads allow-presentation allow-pointer-lock allow-top-navigation"
            @load="onFrameLoaded"
          />

          <!-- Quick Connect Overlay / Companion Helper Banner -->
          <div
            v-if="showCompanionPrompt"
            class="absolute bottom-4 right-4 max-w-sm p-4 bg-surface-white border border-surface-gray-3 rounded-lg shadow-lg flex flex-col gap-2 z-20"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-center gap-2 font-medium text-ink-gray-9 text-sm">
                <WhatsAppIcon class="size-4 text-[#25D366]" />
                <span>{{ __('WhatsApp Web In-CRM') }}</span>
              </div>
              <button
                class="text-ink-gray-4 hover:text-ink-gray-7 text-xs"
                @click="showCompanionPrompt = false"
              >
                ✕
              </button>
            </div>
            <p class="text-xs text-ink-gray-6 leading-relaxed">
              {{ __('If WhatsApp Web does not display inside the frame due to your browser origin policy, click App Window to run a dedicated seamless window.') }}
            </p>
            <div class="flex items-center gap-2 pt-1">
              <Button
                variant="solid"
                size="sm"
                :label="__('Open App Window')"
                @click="openPopoutWindow"
              />
              <Button
                variant="subtle"
                size="sm"
                :label="__('Dismiss')"
                @click="showCompanionPrompt = false"
              />
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import WhatsAppIcon from '@/components/Icons/WhatsAppIcon.vue'
import { FeatherIcon, Button, usePageMeta } from 'frappe-ui'
import { ref } from 'vue'

const currentUrl = ref('https://web.whatsapp.com/')
const frameKey = ref(1)
const isFullscreen = ref(false)
const showCompanionPrompt = ref(true)
const browserContainer = ref(null)

function reloadFrame() {
  frameKey.value++
}

function resetUrl() {
  currentUrl.value = 'https://web.whatsapp.com/'
  frameKey.value++
}

function openPopoutWindow() {
  const width = Math.min(1200, window.screen.availWidth - 100)
  const height = Math.min(850, window.screen.availHeight - 100)
  const left = Math.max(0, (window.screen.availWidth - width) / 2)
  const top = Math.max(0, (window.screen.availHeight - height) / 2)
  
  window.open(
    'https://web.whatsapp.com/',
    'WhatsAppInCRM',
    `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes`
  )
}

function openNewTab() {
  window.open('https://web.whatsapp.com/', '_blank', 'noopener,noreferrer')
}

function toggleFullscreen() {
  if (!browserContainer.value) return
  if (!document.fullscreenElement) {
    browserContainer.value.requestFullscreen().then(() => {
      isFullscreen.value = true
    }).catch(() => {})
  } else {
    document.exitFullscreen().then(() => {
      isFullscreen.value = false
    }).catch(() => {})
  }
}

function onFrameLoaded() {
  // Loaded
}

usePageMeta(() => {
  return { title: __('WhatsApp') }
})
</script>
