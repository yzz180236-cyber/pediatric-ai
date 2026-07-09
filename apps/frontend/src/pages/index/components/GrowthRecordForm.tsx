import React from "react";
import { View } from "@tarojs/components";
import { Input, Button } from "@nutui/nutui-react-taro";

interface GrowthRecordFormProps {
  newAgeMonths: string;
  setNewAgeMonths: (val: string) => void;
  newWeight: string;
  setNewWeight: (val: string) => void;
  newHeight: string;
  setNewHeight: (val: string) => void;
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
  newHeight,
  setNewHeight,
  handleAddRecord,
  editing,
  onCancelEdit,
  saving,
}) => {
  return (
    <View className="growth-record-card micro-growth-form">
      <View className="micro-growth-form-head">
        <View className="micro-growth-form-badge">{editing ? "修改中" : "快速录入"}</View>
        <View className="micro-growth-form-note">月龄 / 体重 / 身高</View>
      </View>

      <View className="micro-growth-grid">
        <View className="micro-growth-field">
          <View className="micro-growth-label">月龄</View>
          <Input
            placeholder="如 4"
            type="number"
            value={newAgeMonths}
            onChange={(value) => setNewAgeMonths(value.replace(/[^\d]/g, ""))}
            className="record-input micro-growth-input"
          />
        </View>

        <View className="micro-growth-field">
          <View className="micro-growth-label">体重</View>
          <Input
            placeholder="kg"
            type="text"
            value={newWeight}
            onChange={(value) => {
              const sanitizedValue = value.replace(/[^\d.]/g, '').replace(/(\..*)\./g, '$1');
              const normalizedValue = sanitizedValue.match(/^\d*(?:\.\d{0,2})?/)?.[0] ?? '';
              setNewWeight(normalizedValue);
            }}
            className="record-input micro-growth-input"
          />
        </View>

        <View className="micro-growth-field">
          <View className="micro-growth-label">身高</View>
          <Input
            placeholder="cm"
            type="text"
            value={newHeight}
            onChange={(value) => {
              const sanitizedValue = value.replace(/[^\d.]/g, '').replace(/(\..*)\./g, '$1');
              const normalizedValue = sanitizedValue.match(/^\d*(?:\.\d{0,2})?/)?.[0] ?? '';
              setNewHeight(normalizedValue);
            }}
            className="record-input micro-growth-input"
          />
        </View>
      </View>

      <View className="micro-growth-actions">
        {editing && (
          <Button
            fill="none"
            onClick={onCancelEdit}
            disabled={saving}
            className="micro-growth-cancel"
          >
            取消
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleAddRecord}
          loading={saving}
          disabled={saving}
          className="record-save-btn micro-growth-submit"
        >
          {saving ? '保存中...' : editing ? '保存修改' : '保存'}
        </Button>
      </View>
    </View>
  );
};
