"use client"

import { create } from "zustand"
import {
  archiveNode as archiveNodeRequest,
  createNode as createNodeRequest,
  listNodes,
  NodePayload,
  NodeResponse,
  NodeUpdatePayload,
  updateNode as updateNodeRequest,
} from "@/lib/vault/api"

interface VaultFilter {
  type: string | null
  search: string
}

interface VaultStore {
  nodes: NodeResponse[]
  isLoading: boolean
  error: string | null
  filter: VaultFilter
  cursor: string | null
  hasMore: boolean
  fetchNodes: () => Promise<void>
  loadMore: () => Promise<void>
  setFilter: (filter: Partial<VaultFilter>) => void
  createNode: (data: NodePayload) => Promise<NodeResponse>
  updateNode: (id: string, data: NodeUpdatePayload) => Promise<NodeResponse>
  archiveNode: (id: string) => Promise<void>
  updateNodeLocally: (node: Partial<NodeResponse> & { id: string }) => void
}

export const useVaultStore = create<VaultStore>((set, get) => ({
  nodes: [],
  isLoading: false,
  error: null,
  filter: { type: null, search: "" },
  cursor: null,
  hasMore: false,

  async fetchNodes() {
    const { filter } = get()
    set({ isLoading: true, error: null })
    try {
      const response = await listNodes({
        type: filter.type,
        search: filter.search.trim() || null,
        limit: 20,
      })
      set({
        nodes: response.nodes,
        cursor: response.cursor,
        hasMore: Boolean(response.cursor),
        isLoading: false,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not load nodes.", isLoading: false })
    }
  },

  async loadMore() {
    const { cursor, filter, nodes } = get()
    if (!cursor) return
    set({ isLoading: true, error: null })
    try {
      const response = await listNodes({
        type: filter.type,
        search: filter.search.trim() || null,
        cursor,
        limit: 20,
      })
      set({
        nodes: [...nodes, ...response.nodes],
        cursor: response.cursor,
        hasMore: Boolean(response.cursor),
        isLoading: false,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Could not load more nodes.", isLoading: false })
    }
  },

  setFilter(filter) {
    set((state) => ({ filter: { ...state.filter, ...filter }, cursor: null }))
  },

  async createNode(data) {
    const node = await createNodeRequest(data)
    set((state) => ({ nodes: [node, ...state.nodes] }))
    return node
  },

  async updateNode(id, data) {
    const node = await updateNodeRequest(id, data)
    set((state) => ({
      nodes: state.nodes.map((existing) => (existing.id === id ? node : existing)),
    }))
    return node
  },

  async archiveNode(id) {
    await archiveNodeRequest(id)
    set((state) => ({ nodes: state.nodes.filter((node) => node.id !== id) }))
  },

  updateNodeLocally(node) {
    set((state) => ({
      nodes: state.nodes.map((existing) =>
        existing.id === node.id ? { ...existing, ...node } : existing
      ),
    }))
  },
}))
