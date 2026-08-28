<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-gray-2">
    <!-- CRM Top Header -->
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-3">
          <div class="flex items-center gap-2 px-1 py-1 text-lg font-semibold text-ink-gray-9">
            <WhatsAppIcon class="size-5 text-[#25D366]" />
            <span>{{ __('WhatsApp') }}</span>
          </div>

          <!-- View Mode Selector Tabs -->
          <div class="flex items-center bg-surface-gray-3 p-0.5 rounded-lg border border-surface-gray-4 text-xs font-medium">
            <button
              class="px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5"
              :class="activeMode === 'browser' ? 'bg-surface-white text-ink-gray-9 shadow-sm font-semibold' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="activeMode = 'browser'"
            >
              <FeatherIcon name="globe" class="size-3.5 text-[#25D366]" />
              <span>{{ __('WhatsApp Web Browser') }}</span>
            </button>
            <button
              class="px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5"
              :class="activeMode === 'messenger' ? 'bg-surface-white text-ink-gray-9 shadow-sm font-semibold' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="activeMode = 'messenger'"
            >
              <FeatherIcon name="message-square" class="size-3.5 text-ink-blue-3" />
              <span>{{ __('CRM Live Messenger') }}</span>
            </button>
            <button
              class="px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5"
              :class="activeMode === 'direct' ? 'bg-surface-white text-ink-gray-9 shadow-sm font-semibold' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="activeMode = 'direct'"
            >
              <FeatherIcon name="send" class="size-3.5 text-emerald-600" />
              <span>{{ __('Direct Chat') }}</span>
            </button>
          </div>
        </div>
      </template>

      <template #right-header>
        <Button
          v-if="activeMode === 'browser'"
          :label="__('Reload Frame')"
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
          @click="openAppWindow"
        />
        <Button
          :label="__('Open Tab')"
          iconLeft="arrow-up-right"
          variant="subtle"
          size="sm"
          @click="openNewTab"
        />
      </template>
    </LayoutHeader>

    <!-- Main Workspace -->
    <div class="flex-1 p-2 sm:p-3 overflow-hidden flex flex-col">

      <!-- MODE 1: In-Built WhatsApp Web Browser -->
      <div
        v-show="activeMode === 'browser'"
        class="flex-1 flex flex-col rounded-lg border border-surface-gray-3 bg-surface-white shadow-sm overflow-hidden"
      >
        <!-- Browser Toolbar -->
        <div class="flex items-center justify-between px-3 py-2 bg-surface-gray-2 border-b border-surface-gray-3 gap-3">
          <div class="flex items-center gap-1">
            <button
              class="p-1.5 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Reload Frame"
              @click="reloadFrame"
            >
              <FeatherIcon name="rotate-cw" class="size-3.5" />
            </button>
            <button
              class="p-1.5 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Reset URL"
              @click="resetUrl"
            >
              <FeatherIcon name="home" class="size-3.5" />
            </button>
          </div>

          <!-- Address Bar -->
          <div class="flex-1 max-w-2xl flex items-center gap-2 px-3 py-1 bg-surface-white rounded border border-surface-gray-3 shadow-inner text-xs text-ink-gray-7">
            <FeatherIcon name="lock" class="size-3 text-emerald-600 flex-shrink-0" />
            <span class="truncate select-all font-mono text-ink-gray-8">{{ currentUrl }}</span>
            <span class="ml-auto text-3xs px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-sans font-medium">SSL Encrypted</span>
          </div>

          <div class="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="subtle"
              :label="__('Fullscreen')"
              iconLeft="maximize-2"
              @click="toggleFullscreen"
            />
          </div>
        </div>

        <!-- Embedded Webview Container -->
        <div class="relative flex-1 w-full h-full bg-[#111b21] overflow-hidden" ref="browserContainer">
          <iframe
            v-if="frameKey"
            :key="frameKey"
            id="whatsapp-web-inapp-frame"
            :src="currentUrl"
            class="w-full h-full border-0 bg-surface-white"
            allow="camera; microphone; clipboard-read; clipboard-write; notifications; display-capture"
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals allow-downloads allow-presentation allow-pointer-lock allow-top-navigation"
          />

          <!-- In-App Browser Assistant Panel (Floating Companion) -->
          <div
            v-if="showAssistant"
            class="absolute bottom-4 right-4 max-w-md p-4 bg-surface-white border border-surface-gray-3 rounded-xl shadow-2xl flex flex-col gap-3 z-30 animate-in fade-in"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-center gap-2 font-semibold text-ink-gray-9 text-sm">
                <WhatsAppIcon class="size-4 text-[#25D366]" />
                <span>{{ __('WhatsApp In-App Companion') }}</span>
              </div>
              <button
                class="text-ink-gray-4 hover:text-ink-gray-7 text-xs p-1"
                @click="showAssistant = false"
              >
                ✕
              </button>
            </div>
            <p class="text-xs text-ink-gray-6 leading-relaxed">
              {{ __('WhatsApp Web is running inside this workspace. If your browser blocks embedding web.whatsapp.com due to security policy, use CRM Live Messenger tab or App Window.') }}
            </p>
            <div class="flex items-center gap-2 pt-1">
              <Button
                variant="solid"
                size="sm"
                :label="__('Switch to CRM Live Messenger')"
                @click="activeMode = 'messenger'"
              />
              <Button
                variant="outline"
                size="sm"
                :label="__('Open App Window')"
                @click="openAppWindow"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- MODE 2: CRM Live WhatsApp Messenger UI -->
      <div
        v-show="activeMode === 'messenger'"
        class="flex-1 flex rounded-lg border border-surface-gray-3 bg-surface-white shadow-sm overflow-hidden"
      >
        <!-- Left Sidebar: Conversations & Contacts -->
        <div class="w-80 border-r border-surface-gray-3 flex flex-col bg-surface-gray-1">
          <!-- Search Header -->
          <div class="p-3 border-b border-surface-gray-3 bg-surface-white">
            <div class="relative flex items-center">
              <FeatherIcon name="search" class="absolute left-3 size-3.5 text-ink-gray-4" />
              <input
                v-model="searchQuery"
                type="text"
                :placeholder="__('Search leads or messages...')"
                class="w-full pl-9 pr-3 py-1.5 bg-surface-gray-2 border border-surface-gray-3 rounded-lg text-xs text-ink-gray-8 placeholder-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          <!-- Conversation List -->
          <div class="flex-1 overflow-y-auto divide-y divide-surface-gray-2">
            <div
              v-for="conv in filteredConversations"
              :key="conv.name"
              class="p-3 flex items-start gap-3 cursor-pointer transition-colors"
              :class="selectedLead?.name === conv.name ? 'bg-surface-gray-2 border-l-4 border-[#25D366]' : 'hover:bg-surface-gray-2'"
              @click="selectConversation(conv)"
            >
              <div class="size-10 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm flex-shrink-0">
                {{ (conv.lead_name || conv.name || 'W').charAt(0).toUpperCase() }}
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between mb-0.5">
                  <h4 class="text-xs font-semibold text-ink-gray-9 truncate">{{ conv.lead_name || conv.name }}</h4>
                  <span class="text-3xs text-ink-gray-4">{{ conv.time || 'Today' }}</span>
                </div>
                <p class="text-xs text-ink-gray-5 truncate">{{ conv.mobile_no || conv.phone || 'No phone' }}</p>
                <div class="flex items-center gap-1 mt-1">
                  <span class="text-3xs px-1.5 py-0.2 rounded bg-surface-gray-3 text-ink-gray-6">{{ conv.status || 'Lead' }}</span>
                </div>
              </div>
            </div>

            <div v-if="!filteredConversations.length" class="p-6 text-center text-ink-gray-4 text-xs">
              {{ __('No active leads found.') }}
            </div>
          </div>
        </div>

        <!-- Right Main: Active Chat Thread & Composer -->
        <div class="flex-1 flex flex-col bg-[#efeae2] relative overflow-hidden">
          <!-- Chat Header -->
          <div class="h-14 px-4 bg-surface-white border-b border-surface-gray-3 flex items-center justify-between z-10">
            <div class="flex items-center gap-3">
              <div class="size-9 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-sm">
                {{ (selectedLead?.lead_name || 'W').charAt(0).toUpperCase() }}
              </div>
              <div>
                <h3 class="text-sm font-semibold text-ink-gray-9">{{ selectedLead?.lead_name || 'Select a Lead to Chat' }}</h3>
                <p class="text-xs text-ink-gray-5 flex items-center gap-1.5">
                  <span>{{ selectedLead?.mobile_no || 'WhatsApp Connected' }}</span>
                  <span class="size-1.5 rounded-full bg-emerald-500"></span>
                  <span class="text-emerald-600 text-3xs font-medium">Online</span>
                </p>
              </div>
            </div>

            <div v-if="selectedLead" class="flex items-center gap-2">
              <router-link
                :to="{ name: 'Lead', params: { leadId: selectedLead.name } }"
                class="px-2.5 py-1 text-xs bg-surface-gray-2 hover:bg-surface-gray-3 text-ink-gray-7 rounded border border-surface-gray-3 font-medium transition-colors"
              >
                {{ __('Open Lead Record') }}
              </router-link>
            </div>
          </div>

          <!-- Chat Messages Scroll Area -->
          <div class="flex-1 overflow-y-auto p-4 space-y-3" ref="messagesContainer">
            <div
              v-for="(msg, idx) in currentMessages"
              :key="idx"
              class="flex"
              :class="msg.type === 'Outgoing' ? 'justify-end' : 'justify-start'"
            >
              <div
                class="max-w-[70%] rounded-lg px-3 py-2 shadow-sm text-xs relative"
                :class="msg.type === 'Outgoing' ? 'bg-[#d9fdd3] text-ink-gray-9 rounded-tr-none' : 'bg-surface-white text-ink-gray-9 rounded-tl-none'"
              >
                <p class="leading-relaxed break-words whitespace-pre-wrap">{{ msg.message }}</p>
                <div class="flex items-center justify-end gap-1 mt-1 text-3xs text-ink-gray-4">
                  <span>{{ msg.time || 'Just now' }}</span>
                  <FeatherIcon v-if="msg.type === 'Outgoing'" name="check" class="size-3 text-blue-500" />
                </div>
              </div>
            </div>

            <div v-if="!currentMessages.length" class="h-full flex flex-col items-center justify-center text-ink-gray-4 text-xs">
              <WhatsAppIcon class="size-12 text-[#25D366] opacity-40 mb-2" />
              <p>{{ __('Send a message below to start communicating with this lead.') }}</p>
            </div>
          </div>

          <!-- Chat Input Bar -->
          <div class="p-3 bg-surface-white border-t border-surface-gray-3 flex items-center gap-2">
            <input
              v-model="newMessageText"
              type="text"
              :placeholder="__('Type a message...')"
              class="flex-1 px-4 py-2 bg-surface-gray-2 border border-surface-gray-3 rounded-full text-xs text-ink-gray-9 placeholder-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              @keydown.enter="sendChatMessage"
            />
            <Button
              variant="solid"
              class="!rounded-full !bg-[#25D366] hover:!bg-[#20bd5a] text-white"
              iconRight="send"
              :disabled="!newMessageText.trim() || !selectedLead"
              @click="sendChatMessage"
            />
          </div>
        </div>
      </div>

      <!-- MODE 3: Direct Chat Launch -->
      <div
        v-show="activeMode === 'direct'"
        class="flex-1 flex flex-col items-center justify-center rounded-lg border border-surface-gray-3 bg-surface-white shadow-sm p-6"
      >
        <div class="max-w-md w-full flex flex-col gap-4">
          <div class="text-center">
            <WhatsAppIcon class="size-12 text-[#25D366] mx-auto mb-2" />
            <h2 class="text-lg font-bold text-ink-gray-9">{{ __('Direct WhatsApp Message') }}</h2>
            <p class="text-xs text-ink-gray-5">{{ __('Start a chat with any number instantly without saving to contacts.') }}</p>
          </div>

          <div class="flex flex-col gap-3 pt-2">
            <div>
              <label class="block text-xs font-medium text-ink-gray-7 mb-1">{{ __('Phone Number (with Country Code)') }}</label>
              <input
                v-model="directPhone"
                type="text"
                placeholder="+971501234567"
                class="w-full px-3 py-2 bg-surface-gray-1 border border-surface-gray-3 rounded-lg text-sm text-ink-gray-9 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono"
              />
            </div>

            <div>
              <label class="block text-xs font-medium text-ink-gray-7 mb-1">{{ __('Message (Optional)') }}</label>
              <textarea
                v-model="directMessage"
                rows="3"
                placeholder="Hi, I am reaching out regarding your inquiry..."
                class="w-full px-3 py-2 bg-surface-gray-1 border border-surface-gray-3 rounded-lg text-xs text-ink-gray-9 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>

            <Button
              variant="solid"
              class="w-full !bg-[#25D366] hover:!bg-[#20bd5a] text-white font-semibold py-2"
              :label="__('Start Chat on WhatsApp')"
              iconRight="arrow-up-right"
              @click="launchDirectChat"
            />
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import WhatsAppIcon from '@/components/Icons/WhatsAppIcon.vue'
import { FeatherIcon, Button, usePageMeta, createResource, toast } from 'frappe-ui'
import { ref, computed, onMounted, nextTick } from 'vue'

const activeMode = ref('browser')
const currentUrl = ref('https://web.whatsapp.com/')
const frameKey = ref(1)
const isFullscreen = ref(false)
const showAssistant = ref(true)
const browserContainer = ref(null)

const searchQuery = ref('')
const selectedLead = ref(null)
const newMessageText = ref('')
const directPhone = ref('')
const directMessage = ref('')
const messagesContainer = ref(null)

// Leads Resource
const leadsResource = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: 'CRM Lead',
    fields: ['name', 'lead_name', 'mobile_no', 'status', 'modified'],
    limit_page_length: 50,
    order_by: 'modified desc',
  },
  auto: true,
  onSuccess(data) {
    if (data && data.length && !selectedLead.value) {
      selectedLead.value = data[0]
      loadLeadMessages(data[0])
    }
  },
})

const filteredConversations = computed(() => {
  const list = leadsResource.data || []
  if (!searchQuery.value) return list
  const q = searchQuery.value.toLowerCase()
  return list.filter(
    (l) =>
      (l.lead_name && l.lead_name.toLowerCase().includes(q)) ||
      (l.mobile_no && l.mobile_no.includes(q)) ||
      (l.name && l.name.toLowerCase().includes(q))
  )
})

const currentMessages = ref([
  { type: 'Incoming', message: 'Hello! I am inquiring about your visa services.', time: '10:30 AM' },
  { type: 'Outgoing', message: 'Welcome to Middle East Holidays! How can we assist you today?', time: '10:31 AM' },
])

function selectConversation(conv) {
  selectedLead.value = conv
  loadLeadMessages(conv)
}

function loadLeadMessages(lead) {
  if (!lead) return
  createResource({
    url: 'crm.api.whatsapp.get_whatsapp_messages',
    params: {
      reference_doctype: 'CRM Lead',
      reference_name: lead.name,
    },
    auto: true,
    onSuccess(data) {
      if (data && data.length) {
        currentMessages.value = data.map(m => ({
          type: m.type || m.direction || 'Outgoing',
          message: m.message || '',
          time: m.creation ? m.creation.split(' ')[1]?.slice(0, 5) : 'Now'
        }))
      } else {
        currentMessages.value = [
          { type: 'Incoming', message: 'Inquiry initialized for ' + (lead.lead_name || lead.name), time: 'Today' }
        ]
      }
      scrollToBottom()
    }
  })
}

function sendChatMessage() {
  if (!newMessageText.value.trim() || !selectedLead.value) return
  const text = newMessageText.value.trim()
  
  currentMessages.value.push({
    type: 'Outgoing',
    message: text,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  })
  
  newMessageText.value = ''
  scrollToBottom()

  createResource({
    url: 'crm.api.whatsapp.create_whatsapp_message',
    params: {
      reference_doctype: 'CRM Lead',
      reference_name: selectedLead.value.name,
      message: text,
      to: selectedLead.value.mobile_no || '',
    },
    auto: true,
    onError(err) {
      toast.error(err.messages?.[0] || 'Failed to sync message')
    }
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function reloadFrame() {
  frameKey.value++
}

function resetUrl() {
  currentUrl.value = 'https://web.whatsapp.com/'
  frameKey.value++
}

function openAppWindow() {
  const width = Math.min(1200, window.screen.availWidth - 80)
  const height = Math.min(850, window.screen.availHeight - 80)
  const left = Math.max(0, (window.screen.availWidth - width) / 2)
  const top = Math.max(0, (window.screen.availHeight - height) / 2)

  window.open(
    'https://web.whatsapp.com/',
    'WhatsAppWebCRM',
    `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes`
  )
}

function openNewTab() {
  window.open('https://web.whatsapp.com/', '_blank', 'noopener,noreferrer')
}

function launchDirectChat() {
  if (!directPhone.value.trim()) {
    toast.error('Please enter a phone number')
    return
  }
  const cleanPhone = directPhone.value.replace(/[^0-9]/g, '')
  const text = encodeURIComponent(directMessage.value.trim())
  const url = `https://web.whatsapp.com/send?phone=${cleanPhone}&text=${text}`
  window.open(url, '_blank', 'noopener,noreferrer')
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

usePageMeta(() => {
  return { title: __('WhatsApp') }
})
</script>
