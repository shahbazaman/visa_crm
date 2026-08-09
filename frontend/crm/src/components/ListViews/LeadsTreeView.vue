<template>
  <div class="flex flex-col h-full bg-white">
    <!-- Header / Navigation Bar -->
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50 gap-4">
      <!-- Breadcrumb & Back Button -->
      <div class="flex items-center gap-3">
        <Button
          v-if="currentCategory"
          variant="subtle"
          size="sm"
          icon="arrow-left"
          @click="goBack"
        />
        <div class="flex items-center text-sm font-medium text-ink-gray-7 gap-2 flex-wrap">
          <span
            class="cursor-pointer hover:text-blue-600 transition-colors"
            @click="goToCategories"
          >
            Leads
          </span>
          <template v-if="currentCategory">
            <span class="text-ink-gray-4">/</span>
            <span
              class="cursor-pointer hover:text-blue-600 transition-colors"
              :class="{ 'font-semibold text-ink-gray-9': !currentSubcategory }"
              @click="goToSubcategories"
            >
              {{ currentCategory }}
            </span>
          </template>
          <template v-if="currentSubcategory">
            <span class="text-ink-gray-4">/</span>
            <span class="font-semibold text-ink-gray-9">
              {{ currentSubcategory }}
            </span>
          </template>
        </div>
      </div>

      <!-- Filters & Search (Visible on Page 3: Lead List) -->
      <div v-if="currentCategory && currentSubcategory" class="flex items-center gap-3 w-full sm:w-auto">
        <!-- Search Input -->
        <div class="relative flex-1 sm:w-64">
          <FeatherIcon name="search" class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-gray-4" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search leads..."
            class="w-full pl-9 pr-3 py-1.5 text-sm bg-white border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500"
            @input="onSearchInput"
          />
        </div>

        <!-- Status Filter -->
        <select
          v-model="selectedStatus"
          class="text-sm bg-white border border-gray-200 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500 text-ink-gray-8"
          @change="onStatusChange"
        >
          <option value="">All Statuses</option>
          <option v-for="st in statusOptions" :key="st" :value="st">{{ st }}</option>
        </select>

        <Button
          v-if="searchQuery || selectedStatus"
          variant="ghost"
          size="sm"
          label="Clear"
          @click="clearFilters"
        />
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="flex-1 overflow-y-auto p-6">
      <!-- PAGE 1: CATEGORIES VIEW -->
      <template v-if="!currentCategory">
        <div v-if="loadingCategories" class="p-12 text-center text-ink-gray-5">
          <Spinner class="w-6 h-6 mx-auto mb-2 text-blue-500" />
          {{ __('Loading Categories...') }}
        </div>
        <EmptyState
          v-else-if="categories.length === 0"
          title="No Categories Found"
          description="No lead categories are currently available."
          icon="folder"
        />
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <div
            v-for="cat in categories"
            :key="cat.value"
            class="p-5 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group flex flex-col justify-between h-36"
            @click="selectCategory(cat)"
          >
            <div class="flex items-start justify-between">
              <div class="p-2.5 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-600 group-hover:text-white transition-colors">
                <FeatherIcon name="folder" class="w-6 h-6" />
              </div>
              <span class="text-xs font-semibold px-2.5 py-1 bg-gray-100 text-ink-gray-7 rounded-full">
                {{ cat.count }} {{ cat.count === 1 ? 'Lead' : 'Leads' }}
              </span>
            </div>
            <div class="mt-4">
              <h3 class="text-base font-semibold text-ink-gray-9 group-hover:text-blue-600 transition-colors truncate">
                {{ cat.label }}
              </h3>
              <p class="text-xs text-ink-gray-5 mt-0.5">Click to view subcategories</p>
            </div>
          </div>
        </div>
      </template>

      <!-- PAGE 2: SUBCATEGORIES VIEW -->
      <template v-else-if="currentCategory && !currentSubcategory">
        <div v-if="loadingSubcategories" class="p-12 text-center text-ink-gray-5">
          <Spinner class="w-6 h-6 mx-auto mb-2 text-indigo-500" />
          {{ __('Loading Subcategories for ') }} {{ currentCategory }}...
        </div>
        <EmptyState
          v-else-if="subcategories.length === 0"
          title="No Subcategories Found"
          description="There are no subcategories under this category."
          icon="layers"
        />
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <div
            v-for="sub in subcategories"
            :key="sub.value"
            class="p-5 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-indigo-300 transition-all cursor-pointer group flex flex-col justify-between h-36"
            @click="selectSubcategory(sub)"
          >
            <div class="flex items-start justify-between">
              <div class="p-2.5 bg-indigo-50 text-indigo-600 rounded-lg group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                <FeatherIcon name="layers" class="w-6 h-6" />
              </div>
              <span class="text-xs font-semibold px-2.5 py-1 bg-gray-100 text-ink-gray-7 rounded-full">
                {{ sub.count }} {{ sub.count === 1 ? 'Lead' : 'Leads' }}
              </span>
            </div>
            <div class="mt-4">
              <h3 class="text-base font-semibold text-ink-gray-9 group-hover:text-indigo-600 transition-colors truncate">
                {{ sub.label }}
              </h3>
              <p class="text-xs text-ink-gray-5 mt-0.5">Click to view lead list</p>
            </div>
          </div>
        </div>
      </template>

      <!-- PAGE 3: LEADS LIST TABLE VIEW -->
      <template v-else-if="currentCategory && currentSubcategory">
        <div v-if="loadingLeads && leadsData.length === 0" class="p-12 text-center text-ink-gray-5">
          <Spinner class="w-6 h-6 mx-auto mb-2 text-blue-500" />
          {{ __('Loading Leads for ') }} {{ currentSubcategory }}...
        </div>
        <EmptyState
          v-else-if="!loadingLeads && leadsData.length === 0"
          title="No Leads Found"
          description="No leads match the selected criteria."
          icon="user-x"
        />
        <div v-else class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50/75 text-xs text-ink-gray-5 font-semibold uppercase tracking-wider">
              <tr>
                <th scope="col" class="px-4 py-3 text-left w-10">
                  <input
                    type="checkbox"
                    class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    :checked="isAllSelected"
                    @change="toggleSelectAll"
                  />
                </th>
                <th scope="col" class="px-4 py-3 text-left">Lead Name</th>
                <th scope="col" class="px-4 py-3 text-left">Customer / Contact</th>
                <th scope="col" class="px-4 py-3 text-left">Status</th>
                <th scope="col" class="px-4 py-3 text-left">Owner</th>
                <th scope="col" class="px-4 py-3 text-right">Modified</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 bg-white text-sm">
              <tr
                v-for="lead in leadsData"
                :key="lead.name"
                class="hover:bg-blue-50/40 transition-colors cursor-pointer group"
                @click="openLead(lead)"
              >
                <td class="px-4 py-3" @click.stop>
                  <input
                    type="checkbox"
                    class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    :checked="isSelected(lead.name)"
                    @change="toggleSelection(lead.name)"
                  />
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-3">
                    <Avatar
                      :image="lead.image"
                      :label="lead.first_name || lead.lead_name || lead.name"
                      size="sm"
                    />
                    <div>
                      <div class="font-semibold text-ink-gray-9 group-hover:text-blue-600 transition-colors">
                        {{ lead.lead_name || lead.name }}
                      </div>
                      <div class="text-xs text-ink-gray-5 truncate max-w-xs">
                        {{ lead.name }}
                      </div>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <div class="text-ink-gray-8 font-medium truncate max-w-xs">
                    {{ lead.customer || lead.organization || '—' }}
                  </div>
                  <div class="text-xs text-ink-gray-5 truncate max-w-xs">
                    {{ lead.email_id || lead.mobile_no || 'No contact info' }}
                  </div>
                </td>
                <td class="px-4 py-3">
                  <Badge
                    v-if="lead.status"
                    variant="subtle"
                    :theme="getLeadStatus(lead.status)?.color || 'gray'"
                    size="md"
                    :label="lead.status"
                  />
                </td>
                <td class="px-4 py-3">
                  <div v-if="lead.lead_owner" class="flex items-center gap-2">
                    <Avatar
                      :image="getUser(lead.lead_owner)?.user_image"
                      :label="getUser(lead.lead_owner)?.full_name"
                      size="xs"
                    />
                    <span class="text-xs text-ink-gray-7 truncate">{{ getUser(lead.lead_owner)?.full_name }}</span>
                  </div>
                  <span v-else class="text-xs text-ink-gray-4">Unassigned</span>
                </td>
                <td class="px-4 py-3 text-right text-xs text-ink-gray-5">
                  <Tooltip :text="formatDate(lead.modified)">
                    {{ timeAgo(lead.modified) }}
                  </Tooltip>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Load More Button -->
          <div v-if="hasMoreLeads" class="p-4 border-t border-gray-100 bg-gray-50/50 text-center">
            <Button
              variant="subtle"
              size="sm"
              class="w-full sm:w-auto px-8"
              :loading="loadingMoreLeads"
              @click="loadMore"
            >
              Load More Leads
            </Button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { call, Avatar, Badge, Tooltip, FeatherIcon, Spinner, Button } from 'frappe-ui'
import { useRoute, useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { timeAgo, formatDate } from '@/utils'
import EmptyState from '@/components/ListViews/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const { getUser } = usersStore()
const { getLeadStatus } = statusesStore()

const currentCategory = computed(() => route.query.category || '')
const currentSubcategory = computed(() => route.query.subcategory || '')

const categories = ref([])
const loadingCategories = ref(false)

const subcategories = ref([])
const loadingSubcategories = ref(false)

const leadsData = ref([])
const loadingLeads = ref(false)
const loadingMoreLeads = ref(false)
const hasMoreLeads = ref(false)
const currentPage = ref(1)

const searchQuery = ref('')
const selectedStatus = ref('')

let searchDebounceTimer = null

const statusOptions = [
  'Lead',
  'Open',
  'Contacted',
  'Qualified',
  'Unqualified',
  'Converted',
  'Lost'
]

const selectedLeads = ref(new Set())

const isAllSelected = computed(() => {
  if (leadsData.value.length === 0) return false
  return leadsData.value.every(l => selectedLeads.value.has(l.name))
})

watch(() => [route.query.category, route.query.subcategory], ([cat, sub]) => {
  if (!cat) {
    fetchCategories()
  } else if (cat && !sub) {
    fetchSubcategories(cat)
  } else if (cat && sub) {
    currentPage.value = 1
    fetchLeads(cat, sub, 1)
  }
}, { immediate: true })

async function fetchCategories() {
  loadingCategories.value = true
  try {
    const data = await call('visa_crm.api.lead_tree.get_lead_tree_nodes', {
      parent_level: 'Categories'
    })
    categories.value = data || []
  } catch (e) {
    console.error("Error fetching categories:", e)
  } finally {
    loadingCategories.value = false
  }
}

async function fetchSubcategories(category) {
  loadingSubcategories.value = true
  try {
    const data = await call('visa_crm.api.lead_tree.get_lead_tree_nodes', {
      parent_level: 'Subcategories',
      category: category
    })
    subcategories.value = data || []
  } catch (e) {
    console.error("Error fetching subcategories:", e)
  } finally {
    loadingSubcategories.value = false
  }
}

async function fetchLeads(category, subcategory, page = 1) {
  if (page === 1) {
    loadingLeads.value = true
  } else {
    loadingMoreLeads.value = true
  }

  try {
    const filters = {
      page: page,
      page_length: 20
    }
    if (searchQuery.value) filters.search = searchQuery.value
    if (selectedStatus.value) filters.status = selectedStatus.value

    const res = await call('visa_crm.api.lead_tree.get_lead_tree_nodes', {
      parent_level: 'Leads',
      category: category,
      subcategory: subcategory,
      filters: JSON.stringify(filters)
    })

    if (page === 1) {
      leadsData.value = res.data || []
    } else {
      leadsData.value.push(...(res.data || []))
    }
    hasMoreLeads.value = Boolean(res.has_more)
    currentPage.value = page
  } catch (e) {
    console.error("Error fetching leads:", e)
  } finally {
    loadingLeads.value = false
    loadingMoreLeads.value = false
  }
}

function loadMore() {
  if (currentCategory.value && currentSubcategory.value && hasMoreLeads.value) {
    fetchLeads(currentCategory.value, currentSubcategory.value, currentPage.value + 1)
  }
}

function selectCategory(cat) {
  router.push({
    name: 'Leads',
    query: { category: cat.value || cat.label }
  })
}

function selectSubcategory(sub) {
  router.push({
    name: 'Leads',
    query: { category: currentCategory.value, subcategory: sub.value || sub.label }
  })
}

function openLead(lead) {
  router.push({
    name: 'Lead',
    params: { leadId: lead.name },
    hash: '#activity'
  })
}

function goBack() {
  if (currentSubcategory.value) {
    router.push({
      name: 'Leads',
      query: { category: currentCategory.value }
    })
  } else if (currentCategory.value) {
    router.push({ name: 'Leads' })
  }
}

function goToCategories() {
  router.push({ name: 'Leads' })
}

function goToSubcategories() {
  if (currentCategory.value) {
    router.push({
      name: 'Leads',
      query: { category: currentCategory.value }
    })
  }
}

function onSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    if (currentCategory.value && currentSubcategory.value) {
      currentPage.value = 1
      fetchLeads(currentCategory.value, currentSubcategory.value, 1)
    }
  }, 300)
}

function onStatusChange() {
  if (currentCategory.value && currentSubcategory.value) {
    currentPage.value = 1
    fetchLeads(currentCategory.value, currentSubcategory.value, 1)
  }
}

function clearFilters() {
  searchQuery.value = ''
  selectedStatus.value = ''
  if (currentCategory.value && currentSubcategory.value) {
    currentPage.value = 1
    fetchLeads(currentCategory.value, currentSubcategory.value, 1)
  }
}

function isSelected(name) {
  return selectedLeads.value.has(name)
}

function toggleSelection(name) {
  if (selectedLeads.value.has(name)) {
    selectedLeads.value.delete(name)
  } else {
    selectedLeads.value.add(name)
  }
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedLeads.value.clear()
  } else {
    leadsData.value.forEach(l => selectedLeads.value.add(l.name))
  }
}
</script>
