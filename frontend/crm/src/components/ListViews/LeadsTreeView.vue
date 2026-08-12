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

      <!-- Action Buttons & Search/Filters -->
      <div class="flex items-center gap-3 w-full sm:w-auto">
        <!-- New Category Button (On Page 1) -->
        <Button
          v-if="!currentCategory"
          variant="solid"
          size="sm"
          iconLeft="plus"
          label="+ New Category"
          @click="showNewCategoryModal = true"
        />

        <!-- New Subcategory Button (On Page 2) -->
        <Button
          v-if="currentCategory && !currentSubcategory"
          variant="solid"
          size="sm"
          iconLeft="plus"
          label="+ New Sub-category"
          @click="showNewSubcategoryModal = true"
        />

        <!-- Filters & Search (Visible on Page 3: Lead List) -->
        <template v-if="currentCategory && currentSubcategory">
          <!-- Move Selected Leads Button -->
          <Button
            v-if="selectedLeads.size > 0"
            variant="solid"
            size="sm"
            iconLeft="folder"
            :label="`Move (${selectedLeads.size}) Leads`"
            @click="openMoveModalForSelected"
          />

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
        </template>
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
          description="No lead categories are currently available. Click + New Category above to create one."
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
          description="There are no subcategories under this category. Click + New Sub-category above to create one."
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
                <th scope="col" class="px-4 py-3 text-right w-24">Actions</th>
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
                <td class="px-4 py-3 text-right" @click.stop>
                  <Button
                    variant="ghost"
                    size="xs"
                    icon="folder"
                    label="Move"
                    @click="openMoveModalForSingle(lead)"
                  />
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

    <!-- CREATE CATEGORY MODAL -->
    <Dialog v-model="showNewCategoryModal" :options="{ title: 'Create New Category', size: 'md' }">
      <template #body-content>
        <div class="space-y-4 p-4">
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Category Name *</label>
            <input
              v-model="newCategoryName"
              type="text"
              placeholder="e.g. Thailand"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Description (Optional)</label>
            <textarea
              v-model="newCategoryDescription"
              placeholder="Category description..."
              rows="3"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            ></textarea>
          </div>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2 px-4 pb-4">
          <Button variant="subtle" label="Cancel" @click="showNewCategoryModal = false" />
          <Button
            variant="solid"
            label="Create Category"
            :loading="submittingCategory"
            @click="handleCreateCategory"
          />
        </div>
      </template>
    </Dialog>

    <!-- CREATE SUBCATEGORY MODAL -->
    <Dialog v-model="showNewSubcategoryModal" :options="{ title: 'Create New Sub-category', size: 'md' }">
      <template #body-content>
        <div class="space-y-4 p-4">
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Parent Category *</label>
            <select
              v-model="newSubcategoryParent"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 text-ink-gray-8"
            >
              <option v-for="cat in availableCategories" :key="cat.name" :value="cat.name">
                {{ cat.category_name || cat.name }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Sub-category Name *</label>
            <input
              v-model="newSubcategoryName"
              type="text"
              placeholder="e.g. Hot"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Description (Optional)</label>
            <textarea
              v-model="newSubcategoryDescription"
              placeholder="Sub-category description..."
              rows="3"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            ></textarea>
          </div>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2 px-4 pb-4">
          <Button variant="subtle" label="Cancel" @click="showNewSubcategoryModal = false" />
          <Button
            variant="solid"
            label="Create Sub-category"
            :loading="submittingSubcategory"
            @click="handleCreateSubcategory"
          />
        </div>
      </template>
    </Dialog>

    <!-- MOVE LEADS MODAL -->
    <Dialog v-model="showMoveModal" :options="{ title: `Move (${targetLeadNames.length}) Lead(s) to Category`, size: 'md' }">
      <template #body-content>
        <div class="space-y-4 p-4">
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Target Category *</label>
            <select
              v-model="targetCategory"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 text-ink-gray-8"
              @change="onTargetCategoryChange"
            >
              <option value="">Select Category</option>
              <option v-for="cat in availableCategories" :key="cat.name" :value="cat.name">
                {{ cat.category_name || cat.name }}
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Target Sub-category</label>
            <select
              v-model="targetSubcategory"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 text-ink-gray-8"
              @change="onTargetSubcategoryChange"
            >
              <option value="Unspecified">Unspecified / No Subcategory</option>
              <option v-for="sub in targetSubcategoriesList" :key="sub" :value="sub">
                {{ sub }}
              </option>
              <option value="__ADD_NEW_SUBCATEGORY__" class="font-medium text-blue-600">
                + Add New Sub-category
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Reason (Optional)</label>
            <input
              v-model="moveReason"
              type="text"
              placeholder="e.g. Manually moved to Hot lead queue"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2 px-4 pb-4">
          <Button variant="subtle" label="Cancel" @click="showMoveModal = false" />
          <Button
            variant="solid"
            label="Move Lead(s)"
            :loading="submittingMove"
            @click="handleMoveLeads"
          />
        </div>
      </template>
    </Dialog>

    <!-- INLINE CREATE SUBCATEGORY MODAL (From Move Leads Modal) -->
    <Dialog v-model="showInlineSubcategoryModal" :options="{ title: 'Create New Sub-category', size: 'md' }">
      <template #body-content>
        <div class="space-y-4 p-4">
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Parent Category</label>
            <input
              :value="targetCategory"
              type="text"
              disabled
              readonly
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm bg-gray-100 text-ink-gray-6 focus:outline-none cursor-not-allowed"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Sub-category Name *</label>
            <input
              v-model="inlineSubcategoryName"
              type="text"
              placeholder="e.g. Hot Prospects"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              @keyup.enter="handleInlineCreateSubcategory"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-ink-gray-7 mb-1">Description (Optional)</label>
            <textarea
              v-model="inlineSubcategoryDescription"
              placeholder="Sub-category description..."
              rows="3"
              class="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            ></textarea>
          </div>
          <div v-if="inlineSubcategoryError" class="text-xs text-red-600 font-medium">
            {{ inlineSubcategoryError }}
          </div>
        </div>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2 px-4 pb-4">
          <Button variant="subtle" label="Cancel" @click="cancelInlineCreateSubcategory" />
          <Button
            variant="solid"
            label="Create Sub-category"
            :loading="submittingInlineSubcategory"
            @click="handleInlineCreateSubcategory"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { call, Avatar, Badge, Tooltip, FeatherIcon, Spinner, Button, Dialog } from 'frappe-ui'
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

// Modals State
const showNewCategoryModal = ref(false)
const newCategoryName = ref('')
const newCategoryDescription = ref('')
const submittingCategory = ref(false)

const showNewSubcategoryModal = ref(false)
const newSubcategoryParent = ref('')
const newSubcategoryName = ref('')
const newSubcategoryDescription = ref('')
const submittingSubcategory = ref(false)

const showMoveModal = ref(false)
const targetLeadNames = ref([])
const targetCategory = ref('')
const targetSubcategory = ref('Unspecified')
const previousTargetSubcategory = ref('Unspecified')
const moveReason = ref('')
const targetSubcategoriesList = ref([])
const submittingMove = ref(false)
const availableCategories = ref([])

const showInlineSubcategoryModal = ref(false)
const inlineSubcategoryName = ref('')
const inlineSubcategoryDescription = ref('')
const inlineSubcategoryError = ref('')
const submittingInlineSubcategory = ref(false)

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

    const catList = await call('visa_crm.api.lead_management.subcategories', {})
    availableCategories.value = catList.categories || []
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

// Category Creation
async function handleCreateCategory() {
  if (!newCategoryName.value.trim()) return
  submittingCategory.value = true
  try {
    await call('visa_crm.api.lead_management.create_category', {
      category_name: newCategoryName.value.trim(),
      description: newCategoryDescription.value.trim()
    })
    showNewCategoryModal.value = false
    newCategoryName.value = ''
    newCategoryDescription.value = ''
    fetchCategories()
  } catch (e) {
    console.error("Error creating category:", e)
  } finally {
    submittingCategory.value = false
  }
}

// Subcategory Creation
async function handleCreateSubcategory() {
  const parent = newSubcategoryParent.value || currentCategory.value
  if (!parent || !newSubcategoryName.value.trim()) return
  submittingSubcategory.value = true
  try {
    await call('visa_crm.api.lead_management.create_sub_category', {
      sub_category_name: newSubcategoryName.value.trim(),
      parent_category: parent,
      description: newSubcategoryDescription.value.trim()
    })
    showNewSubcategoryModal.value = false
    newSubcategoryName.value = ''
    newSubcategoryDescription.value = ''
    if (currentCategory.value) {
      fetchSubcategories(currentCategory.value)
    }
  } catch (e) {
    console.error("Error creating subcategory:", e)
  } finally {
    submittingSubcategory.value = false
  }
}

// Move Leads
async function openMoveModalForSingle(lead) {
  targetLeadNames.value = [lead.name]
  targetCategory.value = currentCategory.value !== 'Uncategorized' ? currentCategory.value : ''
  targetSubcategory.value = 'Unspecified'
  moveReason.value = ''
  await loadAvailableCategoriesAndSubcategories(targetCategory.value)
  showMoveModal.value = true
}

async function openMoveModalForSelected() {
  targetLeadNames.value = Array.from(selectedLeads.value)
  targetCategory.value = currentCategory.value !== 'Uncategorized' ? currentCategory.value : ''
  targetSubcategory.value = 'Unspecified'
  moveReason.value = ''
  await loadAvailableCategoriesAndSubcategories(targetCategory.value)
  showMoveModal.value = true
}

async function loadAvailableCategoriesAndSubcategories(cat) {
  try {
    const res = await call('visa_crm.api.lead_management.subcategories', { category: cat || null })
    availableCategories.value = res.categories || []
    targetSubcategoriesList.value = res.subcategories || []
    if (cat && !newSubcategoryParent.value) {
      newSubcategoryParent.value = cat
    }
  } catch (e) {
    console.error("Error fetching subcategories for move modal:", e)
  }
}

async function onTargetCategoryChange() {
  previousTargetSubcategory.value = 'Unspecified'
  targetSubcategory.value = 'Unspecified'
  if (targetCategory.value) {
    await loadAvailableCategoriesAndSubcategories(targetCategory.value)
  } else {
    targetSubcategoriesList.value = []
  }
}

function onTargetSubcategoryChange() {
  if (targetSubcategory.value === '__ADD_NEW_SUBCATEGORY__') {
    if (!targetCategory.value) {
      targetSubcategory.value = 'Unspecified'
      return
    }
    inlineSubcategoryName.value = ''
    inlineSubcategoryDescription.value = ''
    inlineSubcategoryError.value = ''
    showInlineSubcategoryModal.value = true
  } else {
    previousTargetSubcategory.value = targetSubcategory.value
  }
}

function cancelInlineCreateSubcategory() {
  showInlineSubcategoryModal.value = false
  inlineSubcategoryError.value = ''
  targetSubcategory.value = previousTargetSubcategory.value || 'Unspecified'
}

async function handleInlineCreateSubcategory() {
  const name = inlineSubcategoryName.value.trim()
  inlineSubcategoryError.value = ''

  if (!name) {
    inlineSubcategoryError.value = 'Sub-category name is required.'
    return
  }

  if (!targetCategory.value) {
    inlineSubcategoryError.value = 'Parent Target Category is required.'
    return
  }

  submittingInlineSubcategory.value = true
  try {
    await call('visa_crm.api.lead_management.create_sub_category', {
      sub_category_name: name,
      parent_category: targetCategory.value,
      description: inlineSubcategoryDescription.value.trim()
    })

    // Refresh subcategory list for targetCategory
    await loadAvailableCategoriesAndSubcategories(targetCategory.value)

    // Auto-select newly created subcategory
    targetSubcategory.value = name
    previousTargetSubcategory.value = name
    showInlineSubcategoryModal.value = false

    // Refresh subcategories list if currently viewing targetCategory
    if (currentCategory.value === targetCategory.value) {
      fetchSubcategories(currentCategory.value)
    }
  } catch (e) {
    const msg = (e && (e.message || (e.messages && e.messages[0]))) || String(e || '')
    if (msg.toLowerCase().includes('already exists')) {
      inlineSubcategoryError.value = `A sub-category named "${name}" already exists under "${targetCategory.value}".`
      await loadAvailableCategoriesAndSubcategories(targetCategory.value)
      if (targetSubcategoriesList.value.includes(name)) {
        targetSubcategory.value = name
        previousTargetSubcategory.value = name
        showInlineSubcategoryModal.value = false
      }
    } else {
      inlineSubcategoryError.value = msg || 'Failed to create sub-category.'
    }
  } finally {
    submittingInlineSubcategory.value = false
  }
}

async function handleMoveLeads() {
  if (!targetCategory.value || targetLeadNames.value.length === 0) return

  // Guard against submitting special option value
  let groupVal = targetSubcategory.value
  if (groupVal === '__ADD_NEW_SUBCATEGORY__' || groupVal === 'Unspecified') {
    groupVal = null
  }

  submittingMove.value = true
  try {
    await call('visa_crm.api.lead_management.bulk_classify', {
      leads: targetLeadNames.value,
      category: targetCategory.value,
      group: groupVal,
      reason: moveReason.value.trim() || 'Moved via CRM Tree View'
    })
    showMoveModal.value = false
    selectedLeads.value.clear()
    targetLeadNames.value = []
    if (currentCategory.value && currentSubcategory.value) {
      currentPage.value = 1
      fetchLeads(currentCategory.value, currentSubcategory.value, 1)
    }
  } catch (e) {
    console.error("Error moving leads:", e)
  } finally {
    submittingMove.value = false
  }
}
</script>
