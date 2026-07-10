import React from 'react';
import { View, Text } from '@tarojs/components';
import { Button } from '@nutui/nutui-react-taro';
import Taro from '@tarojs/taro';
import './index.scss';

interface PEWSEmergencyModalProps {
  visible: boolean;
  triageReason?: string;
  warningSignals?: string[];
}

export function PEWSEmergencyModal({ visible, triageReason, warningSignals }: PEWSEmergencyModalProps) {
  if (!visible) return null;

  const handleCall120 = () => {
    Taro.makePhoneCall({
      phoneNumber: '120',
      fail: (err) => {
        console.error('拨打 120 失败或被取消', err);
        Taro.showToast({ title: '无法呼叫，请直接使用手机拨打 120', icon: 'none' });
      }
    });
  };

  const handleFindHospital = () => {
    // 模拟搜索就近急诊医院：打开地图或者高光提示
    Taro.showLoading({ title: '正在定位就近急诊...' });
    setTimeout(() => {
      Taro.hideLoading();
      Taro.showModal({
        title: '就近医院急诊指南',
        content: '建议立即动身前往：本市儿童医院急诊医学科，或最近的三甲综合医院急诊科。出行请选择打车或急救车，切勿自行驾车耽误黄金救援时段！',
        showCancel: false,
        confirmText: '我知道了'
      });
    }, 800);
  };

  return (
    <View className="pews-emergency-overlay">
      <View className="pews-emergency-card animate-scale-up">
        {/* 顶部警告标志与呼吸动态微光 */}
        <View className="warning-badge-wrapper">
          <View className="warning-badge-pulse" />
          <View className="warning-badge">🚨</View>
        </View>

        <Text className="modal-title">高危重症紧急就医警告</Text>
        
        <View className="warning-intro-box">
          <Text className="warning-intro-text">
            系统已触及【重症分诊熔断阈值】。为切实保障患儿生命安全，AI 对话问诊通道已被强制熔断。请不要等待医生回复！
          </Text>
        </View>

        {/* 危险信号和分诊指征细节展示 */}
        <View className="warning-details-section">
          {warningSignals && warningSignals.length > 0 && (
            <View className="detail-item-block">
              <Text className="detail-label">⚠️ 命中危险信号：</Text>
              <View className="signals-tag-container">
                {warningSignals.map((signal, idx) => (
                  <Text key={idx} className="signal-tag">{signal}</Text>
                ))}
              </View>
            </View>
          )}

          {triageReason && (
            <View className="detail-item-block">
              <Text className="detail-label">📋 分诊评估依据：</Text>
              <Text className="detail-value-text">{triageReason}</Text>
            </View>
          )}
        </View>

        <View className="hospital-alert-box">
          <Text className="hospital-alert-title">🚨 紧急处置指引：</Text>
          <Text className="hospital-alert-body">
            1. 保持患儿呼吸道通畅，侧卧防止误吸；<br />
            2. 立即拨打 120 呼救，或乘车前往就近儿童医院急诊！
          </Text>
        </View>

        {/* 绝对强阻断按钮区 */}
        <View className="emergency-actions-area">
          <Button
            type="danger"
            block
            onClick={handleCall120}
            className="call-120-btn"
          >
            📞 立即呼叫 120 急救
          </Button>
          <Button
            block
            onClick={handleFindHospital}
            className="find-hospital-btn"
          >
            📍 查找就近儿童急诊医院
          </Button>
        </View>
      </View>
    </View>
  );
}
