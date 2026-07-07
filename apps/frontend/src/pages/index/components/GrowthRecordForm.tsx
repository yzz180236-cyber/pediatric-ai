import React from "react";
import { View } from "@tarojs/components";
import { Input, Button } from "@nutui/nutui-react-taro";

interface GrowthRecordFormProps {
  newAgeMonths: string;
  setNewAgeMonths: (val: string) => void;
  newWeight: string;
  setNewWeight: (val: string) => void;
  handleAddRecord: () => void;
  editing: boolean;
  onCancelEdit: () => void;
  saving: boolean;
}

export const GrowthRecordForm: React.FC<GrowthRecordFormProps> = ({
  newAgeMonths,
  setNewAgeMonths,
  newWeight,
  setNewWeight,
  handleAddRecord,
  editing,
  onCancelEdit,
  saving,
}) => {
  return (
    <View className="growth-record-card">
      <View className="card-title">{editing ? "修改体征记录" : "新增体征记录"}</View>
      <View className="record-form-row">
        <Input
          placeholder="月龄 (整数，如 4)"
          type="number"
          value={newAgeMonths}
          onChange={(value) => setNewAgeMonths(value.replace(/[^\d]/g, ""))}
          className="record-input"
        />
        <Input
          placeholder="体重 (kg)"
          type="text"
          value={newWeight}
          onChange={(value) => {
            const sanitizedValue = value.replace(/[^\d.]/g, '').replace(/(\..*)\./g, '$1');
            const normalizedValue = sanitizedValue.match(/^\d*(?:\.\d{0,2})?/)?.[0] ?? '';
            setNewWeight(normalizedValue);
          }}
          className="record-input"
        />
      </View>
      <Button
        type="primary"
        block
        onClick={handleAddRecord}
        loading={saving}
        disabled={saving}
        className="record-save-btn submit-btn-full"
      >
        {saving ? '保存中...' : editing ? '保存修改' : '保存记录'}
      </Button>
      {editing && (
        <Button
          block
          onClick={onCancelEdit}
          disabled={saving}
          className="record-cancel-btn submit-btn-full"
        >
          取消修改
        </Button>
      )}
    </View>
  );
};
