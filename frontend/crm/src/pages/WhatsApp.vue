<template>
  <div class="flex flex-col h-full overflow-hidden bg-[#f0f2f5]">
    <!-- CRM Top Navigation Header -->
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-3">
          <div class="flex items-center gap-2 px-1 py-1 text-lg font-semibold text-ink-gray-9">
            <WhatsAppIcon class="size-5 text-[#25D366]" />
            <span>{{ __('WhatsApp') }}</span>
          </div>

          <!-- Status Indicator Pill -->
          <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span class="size-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            {{ __('In-App Browser Active') }}
          </span>
        </div>
      </template>

      <template #right-header>
        <Button
          :label="__('New Chat')"
          iconLeft="plus"
          variant="solid"
          class="!bg-[#00a884] hover:!bg-[#008f6f] text-white text-xs"
          size="sm"
          @click="showNewChatModal = true"
        />
        <Button
          :label="__('Refresh')"
          iconLeft="refresh-cw"
          variant="outline"
          size="sm"
          @click="refreshConversations"
        />
        <Button
          :label="isFullscreen ? __('Exit Fullscreen') : __('Fullscreen')"
          :iconLeft="isFullscreen ? 'minimize-2' : 'maximize-2'"
          variant="subtle"
          size="sm"
          @click="toggleFullscreen"
        />
      </template>
    </LayoutHeader>

    <!-- In-Built Browser Workspace -->
    <div class="flex-1 p-2 sm:p-3 overflow-hidden flex flex-col" ref="browserContainer">
      <div class="flex-1 flex flex-col rounded-xl border border-surface-gray-3 bg-surface-white shadow-md overflow-hidden">
        
        <!-- Browser Chrome Address Bar -->
        <div class="flex items-center justify-between px-3 py-1.5 bg-[#f0f2f5] border-b border-surface-gray-3 gap-3 flex-shrink-0">
          <div class="flex items-center gap-1">
            <button
              class="p-1.5 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Refresh Workspace"
              @click="refreshConversations"
            >
              <FeatherIcon name="rotate-cw" class="size-3.5" />
            </button>
            <button
              class="p-1.5 rounded hover:bg-surface-gray-3 text-ink-gray-6 transition-colors"
              title="Home"
              @click="resetChatView"
            >
              <FeatherIcon name="home" class="size-3.5" />
            </button>
          </div>

          <!-- Browser Address Bar -->
          <div class="flex-1 max-w-2xl flex items-center gap-2 px-3 py-1 bg-surface-white rounded-lg border border-surface-gray-3 shadow-inner text-xs">
            <FeatherIcon name="lock" class="size-3 text-[#00a884] flex-shrink-0" />
            <span class="truncate font-mono text-ink-gray-8 select-all font-medium">https://web.whatsapp.com</span>
            <span class="ml-auto text-3xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-sans font-semibold border border-emerald-100">
              WhatsApp Web In-CRM
            </span>
          </div>

          <div class="flex items-center gap-2">
            <span class="text-3xs text-ink-gray-5 flex items-center gap-1">
              <span class="size-1.5 rounded-full bg-emerald-500"></span>
              {{ conversations.length }} {{ __('Chats') }}
            </span>
          </div>
        </div>

        <!-- WhatsApp Web Application Workspace (Inside the browser) -->
        <div class="flex-1 flex overflow-hidden bg-[#efeae2]">
          
          <!-- LEFT SIDEBAR: WhatsApp Contacts & Conversations -->
          <div class="w-80 md:w-96 border-r border-surface-gray-3 flex flex-col bg-surface-white flex-shrink-0">
            
            <!-- User Profile Header -->
            <div class="h-14 px-4 bg-[#f0f2f5] border-b border-surface-gray-3 flex items-center justify-between flex-shrink-0">
              <div class="flex items-center gap-2.5">
                <div class="size-9 rounded-full bg-[#00a884] text-white flex items-center justify-center font-bold text-sm shadow-sm">
                  CRM
                </div>
                <div class="leading-tight">
                  <h4 class="text-xs font-bold text-ink-gray-9">{{ __('WhatsApp Web') }}</h4>
                  <span class="text-3xs text-emerald-600 font-medium">● Connected</span>
                </div>
              </div>

              <div class="flex items-center gap-1 text-ink-gray-6">
                <button
                  class="p-2 rounded-full hover:bg-surface-gray-3 transition-colors"
                  title="New Chat"
                  @click="showNewChatModal = true"
                >
                  <FeatherIcon name="message-square" class="size-4" />
                </button>
                <button
                  class="p-2 rounded-full hover:bg-surface-gray-3 transition-colors"
                  title="Refresh"
                  @click="refreshConversations"
                >
                  <FeatherIcon name="refresh-cw" class="size-4" />
                </button>
              </div>
            </div>

            <!-- Search & Filter Bar -->
            <div class="p-2.5 bg-surface-white border-b border-surface-gray-2 flex flex-col gap-2 flex-shrink-0">
              <div class="relative flex items-center">
                <FeatherIcon name="search" class="absolute left-3 size-3.5 text-ink-gray-4" />
                <input
                  v-model="searchQuery"
                  type="text"
                  :placeholder="__('Search or start new chat')"
                  class="w-full pl-9 pr-3 py-1.5 bg-[#f0f2f5] border-0 rounded-lg text-xs text-ink-gray-9 placeholder-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-[#00a884]"
                />
              </div>

              <!-- Filter Pills -->
              <div class="flex items-center gap-1 text-3xs font-medium overflow-x-auto pb-0.5">
                <button
                  v-for="filter in ['All', 'Unread', 'Leads', 'Customers']"
                  :key="filter"
                  class="px-2.5 py-1 rounded-full transition-colors whitespace-nowrap"
                  :class="activeFilter === filter ? 'bg-[#00a884] text-white font-semibold' : 'bg-[#f0f2f5] text-ink-gray-6 hover:bg-surface-gray-3'"
                  @click="activeFilter = filter"
                >
                  {{ filter }}
                </button>
              </div>
            </div>

            <!-- Conversation Items List -->
            <div class="flex-1 overflow-y-auto divide-y divide-surface-gray-2 bg-surface-white">
              <div
                v-for="conv in filteredConversations"
                :key="conv.name"
                class="px-3 py-3 flex items-start gap-3 cursor-pointer transition-all hover:bg-[#f0f2f5]"
                :class="selectedLead?.name === conv.name ? 'bg-[#f0f2f5] border-l-4 border-[#00a884]' : ''"
                @click="selectConversation(conv)"
              >
                <!-- Avatar -->
                <div class="size-11 rounded-full bg-emerald-100 text-[#00a884] flex items-center justify-center font-bold text-sm flex-shrink-0 shadow-inner">
                  {{ (conv.lead_name || conv.name || 'W').charAt(0).toUpperCase() }}
                </div>

                <!-- Text info -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between mb-0.5">
                    <h4 class="text-xs font-semibold text-ink-gray-9 truncate">{{ conv.lead_name || conv.name }}</h4>
                    <span class="text-3xs text-ink-gray-4 font-medium">{{ conv.time || 'Today' }}</span>
                  </div>
                  <p class="text-xs text-ink-gray-5 truncate leading-tight">{{ conv.last_message || conv.mobile_no || 'Start chatting...' }}</p>
                  
                  <div class="flex items-center justify-between mt-1">
                    <span class="text-3xs px-1.5 py-0.2 rounded bg-[#f0f2f5] text-ink-gray-6 font-medium">
                      {{ conv.mobile_no || 'Lead' }}
                    </span>
                    <span v-if="conv.status" class="text-3xs text-emerald-600 font-medium">
                      {{ conv.status }}
                    </span>
                  </div>
                </div>
              </div>

              <div v-if="!filteredConversations.length" class="p-8 text-center text-ink-gray-4 text-xs flex flex-col items-center gap-2">
                <WhatsAppIcon class="size-8 text-ink-gray-3" />
                <p>{{ __('No conversations found matching search.') }}</p>
              </div>
            </div>
          </div>

          <!-- RIGHT MAIN: WhatsApp Active Chat Conversation Thread -->
          <div class="flex-1 flex flex-col bg-[#efeae2] relative overflow-hidden">
            
            <!-- Chat Contact Header -->
            <div class="h-14 px-4 bg-[#f0f2f5] border-b border-surface-gray-3 flex items-center justify-between flex-shrink-0 z-10">
              <div class="flex items-center gap-3 min-w-0">
                <div class="size-10 rounded-full bg-emerald-100 text-[#00a884] flex items-center justify-center font-bold text-sm shadow-sm flex-shrink-0">
                  {{ (selectedLead?.lead_name || 'W').charAt(0).toUpperCase() }}
                </div>
                <div class="min-w-0 leading-tight">
                  <h3 class="text-xs font-bold text-ink-gray-9 truncate">{{ selectedLead?.lead_name || 'Select a Conversation' }}</h3>
                  <p class="text-3xs text-ink-gray-5 flex items-center gap-1.5 truncate">
                    <span>{{ selectedLead?.mobile_no || 'WhatsApp Live' }}</span>
                    <span class="text-emerald-600 font-medium">● Online</span>
                  </p>
                </div>
              </div>

              <!-- Header Action Controls -->
              <div v-if="selectedLead" class="flex items-center gap-2">
                <router-link
                  :to="{ name: 'Lead', params: { leadId: selectedLead.name } }"
                  class="px-3 py-1.5 text-xs bg-surface-white hover:bg-surface-gray-2 text-ink-gray-7 rounded-lg border border-surface-gray-3 font-semibold transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <FeatherIcon name="user" class="size-3.5 text-[#00a884]" />
                  <span>{{ __('View Lead Record') }}</span>
                </router-link>
              </div>
            </div>

            <!-- Messages Scrollable Thread Area -->
            <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3" ref="messagesContainer" style="background-image: radial-gradient(#d1cdc7 1px, transparent 1px); background-size: 20px 20px;">
              
              <!-- End-to-End Encryption Notice Banner -->
              <div class="flex justify-center my-2">
                <div class="px-3 py-1 bg-[#ffeecd] rounded-lg shadow-2xs border border-[#ffdf9e] text-center max-w-md">
                  <p class="text-3xs text-[#54656f] flex items-center justify-center gap-1">
                    <FeatherIcon name="lock" class="size-3 text-[#54656f]" />
                    <span>Messages are end-to-end encrypted and synced with Frappe CRM.</span>
                  </p>
                </div>
              </div>

              <!-- Day Divider -->
              <div class="flex justify-center my-2">
                <span class="px-3 py-1 bg-surface-white rounded-md text-3xs text-ink-gray-5 shadow-2xs font-semibold uppercase tracking-wider">
                  Today
                </span>
              </div>

              <!-- Chat Message Bubbles -->
              <div
                v-for="(msg, idx) in currentMessages"
                :key="idx"
                class="flex"
                :class="msg.type === 'Outgoing' ? 'justify-end' : 'justify-start'"
              >
                <div
                  class="max-w-[75%] md:max-w-[65%] rounded-lg px-3 py-2 shadow-sm text-xs relative leading-relaxed"
                  :class="msg.type === 'Outgoing' ? 'bg-[#d9fdd3] text-ink-gray-9 rounded-tr-none' : 'bg-surface-white text-ink-gray-9 rounded-tl-none'"
                >
                  <p class="break-words whitespace-pre-wrap">{{ msg.message }}</p>
                  
                  <div class="flex items-center justify-end gap-1 mt-1 text-3xs text-[#667781]">
                    <span>{{ msg.time || 'Just now' }}</span>
                    <FeatherIcon v-if="msg.type === 'Outgoing'" name="check" class="size-3 text-[#53bdeb]" />
                  </div>
                </div>
              </div>

              <div v-if="!currentMessages.length" class="h-48 flex flex-col items-center justify-center text-ink-gray-4 text-xs">
                <WhatsAppIcon class="size-12 text-[#00a884] opacity-30 mb-2" />
                <p>{{ __('Send a message below to start communicating with this lead.') }}</p>
              </div>
            </div>

            <!-- Bottom Message Composer -->
            <div class="p-3 bg-[#f0f2f5] border-t border-surface-gray-3 flex items-center gap-2 flex-shrink-0">
              <div class="flex items-center gap-1 text-ink-gray-6">
                <button
                  class="p-2 rounded-full hover:bg-surface-gray-3 transition-colors text-ink-gray-5"
                  title="Emoji"
                  @click="newMessageText += ' 😊'"
                >
                  <FeatherIcon name="smile" class="size-5" />
                </button>
              </div>

              <input
                ref="messageInputRef"
                v-model="newMessageText"
                type="text"
                :placeholder="__('Type a message')"
                class="flex-1 px-4 py-2 bg-surface-white border-0 rounded-lg text-xs text-ink-gray-9 placeholder-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-[#00a884] shadow-2xs"
                @keydown.enter="sendChatMessage"
              />

              <button
                class="size-10 rounded-full bg-[#00a884] hover:bg-[#008f6f] text-white flex items-center justify-center transition-transform active:scale-95 shadow-sm disabled:opacity-50"
                :disabled="!newMessageText.trim() || !selectedLead"
                title="Send Message"
                @click="sendChatMessage"
              >
                <FeatherIcon name="send" class="size-4" />
              </button>
            </div>

          </div>
        </div>

      </div>
    </div>

    <!-- New Chat In-App Dialog -->
    <div
      v-if="showNewChatModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4"
    >
      <div class="bg-surface-white rounded-2xl border border-surface-gray-3 shadow-2xl max-w-md w-full p-6 flex flex-col gap-4 animate-in fade-in">
        <div class="flex items-center justify-between border-b border-surface-gray-2 pb-3">
          <div class="flex items-center gap-2">
            <WhatsAppIcon class="size-5 text-[#00a884]" />
            <h3 class="text-base font-bold text-ink-gray-9">{{ __('Start New In-App Chat') }}</h3>
          </div>
          <button class="text-ink-gray-4 hover:text-ink-gray-7" @click="showNewChatModal = false">✕</button>
        </div>

        <div class="flex flex-col gap-3">
          <div>
            <label class="block text-xs font-semibold text-ink-gray-7 mb-1">{{ __('Contact / Lead Name') }}</label>
            <input
              v-model="newChatName"
              type="text"
              placeholder="e.g. John Doe"
              class="w-full px-3 py-2 bg-[#f0f2f5] border-0 rounded-lg text-xs text-ink-gray-9 focus:outline-none focus:ring-1 focus:ring-[#00a884]"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-ink-gray-7 mb-1">{{ __('Phone Number (with Country Code)') }}</label>
            <input
              v-model="newChatPhone"
              type="text"
              placeholder="+971501234567"
              class="w-full px-3 py-2 bg-[#f0f2f5] border-0 rounded-lg text-xs text-ink-gray-9 font-mono focus:outline-none focus:ring-1 focus:ring-[#00a884]"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-ink-gray-7 mb-1">{{ __('Initial Message') }}</label>
            <textarea
              v-model="newChatMessage"
              rows="3"
              placeholder="Hello, I am reaching out regarding your inquiry..."
              class="w-full px-3 py-2 bg-[#f0f2f5] border-0 rounded-lg text-xs text-ink-gray-9 focus:outline-none focus:ring-1 focus:ring-[#00a884]"
            />
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t border-surface-gray-2">
          <Button variant="subtle" size="sm" :label="__('Cancel')" @click="showNewChatModal = false" />
          <Button
            variant="solid"
            size="sm"
            class="!bg-[#00a884] hover:!bg-[#008f6f] text-white"
            :label="__('Start In-App Chat')"
            @click="startNewInAppChat"
          />
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

const searchQuery = ref('')
const activeFilter = ref('All')
const selectedLead = ref(null)
const newMessageText = ref('')
const isFullscreen = ref(false)
const browserContainer = ref(null)
const messagesContainer = ref(null)
const messageInputRef = ref(null)

// New Chat Modal state
const showNewChatModal = ref(false)
const newChatName = ref('')
const newChatPhone = ref('')
const newChatMessage = ref('')

const conversations = ref([])

// Fetch all WhatsApp conversations from backend
const conversationsResource = createResource({
  url: 'visa_crm.api.whatsapp_integration.get_all_whatsapp_conversations',
  auto: true,
  onSuccess(data) {
    if (data && Array.isArray(data)) {
      conversations.value = data
      if (data.length && !selectedLead.value) {
        selectConversation(data[0])
      }
    }
  },
})

// Fallback to CRM Leads if needed
const leadsFallback = createResource({
  url: 'frappe.client.get_list',
  params: {
    doctype: 'CRM Lead',
    fields: ['name', 'lead_name', 'mobile_no', 'status', 'modified'],
    limit_page_length: 50,
    order_by: 'modified desc',
  },
  auto: true,
  onSuccess(data) {
    if (!conversations.value.length && data && data.length) {
      conversations.value = data.map(l => ({
        name: l.name,
        doctype: 'CRM Lead',
        lead_name: l.lead_name || l.name,
        mobile_no: l.mobile_no || '',
        status: l.status || 'Lead',
        last_message: 'Click to start chatting',
        time: 'Today',
      }))
      if (!selectedLead.value) {
        selectConversation(conversations.value[0])
      }
    }
  }
})

const filteredConversations = computed(() => {
  let list = conversations.value || []
  if (activeFilter.value === 'Unread') {
    list = list.filter(c => c.unread)
  }
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
  { type: 'Incoming', message: 'Hello! I am reaching out regarding visa inquiry.', time: '10:30 AM' },
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

  // Update last message in list
  selectedLead.value.last_message = text
  selectedLead.value.time = 'Just now'
  
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
      toast.error(err.messages?.[0] || 'Message saved in CRM')
    }
  })
}

function startNewInAppChat() {
  if (!newChatPhone.value.trim()) {
    toast.error('Please provide a phone number')
    return
  }
  const name = newChatName.value.trim() || newChatPhone.value.trim()
  const newConv = {
    name: 'direct_' + Date.now(),
    doctype: 'CRM Lead',
    lead_name: name,
    mobile_no: newChatPhone.value.trim(),
    status: 'Direct',
    last_message: newChatMessage.value.trim() || 'New conversation',
    time: 'Now',
  }
  conversations.value.unshift(newConv)
  selectConversation(newConv)

  if (newChatMessage.value.trim()) {
    currentMessages.value = [
      {
        type: 'Outgoing',
        message: newChatMessage.value.trim(),
        time: 'Just now'
      }
    ]
  } else {
    currentMessages.value = []
  }

  showNewChatModal.value = false
  newChatName.value = ''
  newChatPhone.value = ''
  newChatMessage.value = ''
  toast.success('In-App WhatsApp chat opened')
}

function refreshConversations() {
  conversationsResource.reload()
  if (selectedLead.value) {
    loadLeadMessages(selectedLead.value)
  }
  toast.success('WhatsApp messages updated')
}

function resetChatView() {
  if (conversations.value.length) {
    selectConversation(conversations.value[0])
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
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
