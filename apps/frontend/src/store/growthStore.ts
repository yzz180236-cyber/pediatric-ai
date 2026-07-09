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

function sortGrowthRecords(records: GrowthRecordDto[]): GrowthRecordDto[] {
  return [...records].sort((a, b) => {
    if (a.ageMonths !== b.ageMonths) {
      return a.ageMonths - b.ageMonths;
    }
    return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
  });
}

export const useGrowthStore = create<GrowthState>()((set) => ({
  records: [],
  setRecords: (records) => set({ records: sortGrowthRecords(records) }),
  addRecord: (record) => set((state) => ({ records: sortGrowthRecords([...state.records, record]) })),
  updateRecord: (record) =>
    set((state) => ({
      records: sortGrowthRecords(state.records.map((item) => (item.id === record.id ? record : item))),
    })),
  removeRecord: (recordId) =>
    set((state) => ({
      records: sortGrowthRecords(state.records.filter((item) => item.id !== recordId)),
    })),
  clearRecords: () => set({ records: [] }),
}));
