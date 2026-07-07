import { useEffect, useState } from "react";
import Taro from "@tarojs/taro";
import { CreateGrowthRecordRequest, GrowthRecordDto, UpdateGrowthRecordRequest } from "@pediatric-ai/shared-types";
import { ensureAuthenticated, isH5Dev } from "../../../utils/auth";
import { request } from "../../../utils/request";
import { useGrowthStore } from "../../../store/growthStore";
import { useUserStore } from "../../../store/userStore";
import { trackEvent } from "../../../utils/tracker";

export function useGrowthRecords() {
  const { records: growthRecords, setRecords, addRecord, updateRecord, removeRecord } = useGrowthStore();
  const token = useUserStore((state) => state.token);
  const [newAgeMonths, setNewAgeMonths] = useState("");
  const [newWeight, setNewWeight] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingRecordId, setEditingRecordId] = useState<string | null>(null);

  useEffect(() => {
    if (isH5Dev && !token) {
      return;
    }

    const loadGrowthRecords = async () => {
      try {
        await ensureAuthenticated();
        const records = await request<typeof growthRecords>("/patient/growth-records", {
          method: "GET",
        });
        setRecords(records);
      } catch (error) {
        console.error("加载生长记录失败", error);
      }
    };

    loadGrowthRecords();
  }, [setRecords, token]);

  const handleAddRecord = async () => {
    const ageMonths = Number(newAgeMonths);
    const weight = Number(newWeight);

    if (!newAgeMonths.trim()) {
      Taro.showToast({ title: "请输入月龄", icon: "none" });
      return;
    }

    if (!Number.isInteger(ageMonths) || ageMonths < 0 || ageMonths > 72) {
      Taro.showToast({ title: "月龄需为0-72整数", icon: "none" });
      return;
    }

    if (!Number.isFinite(weight) || weight <= 0) {
      Taro.showToast({ title: "请输入正确体重", icon: "none" });
      return;
    }

    setSaving(true);
    try {
      await ensureAuthenticated();
      const payload: CreateGrowthRecordRequest | UpdateGrowthRecordRequest = {
        ageMonths,
        weight,
      };
      if (editingRecordId) {
        const savedRecord = await request<GrowthRecordDto>(`/patient/growth-records/${editingRecordId}`, {
          method: "PUT",
          data: payload,
        });
        updateRecord(savedRecord);
        trackEvent('growth_record_updated', {
          recordId: savedRecord.id,
          ageMonths: savedRecord.ageMonths,
        });
        Taro.showToast({ title: "修改成功", icon: "success" });
      } else {
        const savedRecord = await request<GrowthRecordDto>("/patient/growth-records", {
          method: "POST",
          data: payload,
        });
        addRecord(savedRecord);
        trackEvent('growth_record_created', {
          recordId: savedRecord.id,
          ageMonths: savedRecord.ageMonths,
        });
        Taro.showToast({ title: "保存成功", icon: "success" });
      }
      setNewAgeMonths("");
      setNewWeight("");
      setEditingRecordId(null);
    } catch (error) {
      console.error("保存生长记录失败", error);
    } finally {
      setSaving(false);
    }
  };

  const handleEditRecord = (record: GrowthRecordDto) => {
    setEditingRecordId(record.id);
    setNewAgeMonths(String(record.ageMonths));
    setNewWeight(String(record.weight));
  };

  const handleCancelEdit = () => {
    setEditingRecordId(null);
    setNewAgeMonths("");
    setNewWeight("");
  };

  const handleDeleteRecord = async (record: GrowthRecordDto) => {
    const result = await Taro.showModal({
      title: "删除记录",
      content: `确定删除 ${record.monthLabel} / ${record.weight}kg 这条记录吗？`,
    });
    if (!result.confirm) return;

    try {
      await ensureAuthenticated();
      await request<{ success: true }>(`/patient/growth-records/${record.id}`, {
        method: "DELETE",
      });
      removeRecord(record.id);
      trackEvent('growth_record_deleted', {
        recordId: record.id,
        ageMonths: record.ageMonths,
      });
      if (editingRecordId === record.id) {
        handleCancelEdit();
      }
      Taro.showToast({ title: "删除成功", icon: "success" });
    } catch (error) {
      console.error("删除生长记录失败", error);
    }
  };

  return {
    growthRecords,
    newAgeMonths,
    setNewAgeMonths,
    newWeight,
    setNewWeight,
    editing: editingRecordId !== null,
    saving,
    handleAddRecord,
    handleEditRecord,
    handleCancelEdit,
    handleDeleteRecord,
  };
}
