import { create } from 'zustand';
import { GrowthRecordDto } from '@pediatric-ai/shared-types';

interface GrowthState {
  records: GrowthRecordDto[];
  setRecords: (records: GrowthRecordDto[]) => void;
  addRecord: (record: GrowthRecordDto) => void;
  updateRecord: (record: GrowthRecordDto) => void;
  removeRecord: (recordId: string) => void;
  clearRecords: () => void;
}

export const useGrowthStore = create<GrowthState>()((set) => ({
  records: [],
  setRecords: (records) => set({ records }),
  addRecord: (record) => set((state) => ({ records: [...state.records, record] })),
  updateRecord: (record) =>
    set((state) => ({
      records: state.records.map((item) => (item.id === record.id ? record : item)),
    })),
  removeRecord: (recordId) =>
    set((state) => ({
      records: state.records.filter((item) => item.id !== recordId),
    })),
  clearRecords: () => set({ records: [] }),
}));
