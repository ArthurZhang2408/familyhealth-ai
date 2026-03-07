import { useState } from 'react';
import { View, Pressable, Modal, Dimensions } from 'react-native';
import { Image } from 'expo-image';
import { useColors } from '@/hooks/useColors';
import { Spacing, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/Icon';
import type { MessagePart } from '@/types/api';

type ImagePart = Extract<MessagePart, { type: 'image' }>;

const THUMB_WIDTH = 200;
const THUMB_HEIGHT = 150;

export function ImagePartView({ part }: { part: ImagePart }) {
  const Colors = useColors();
  const [fullscreen, setFullscreen] = useState(false);
  const { width: screenWidth, height: screenHeight } = Dimensions.get('window');

  return (
    <>
      <Pressable onPress={() => setFullscreen(true)}>
        <Image
          source={{ uri: part.url }}
          style={{
            width: THUMB_WIDTH,
            height: THUMB_HEIGHT,
            borderRadius: BorderRadius.lg,
            backgroundColor: Colors.surfaceSecondary,
          }}
          contentFit="cover"
          cachePolicy="disk"
          transition={200}
        />
      </Pressable>
      <Modal visible={fullscreen} transparent animationType="fade">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'center', alignItems: 'center' }}>
          <Pressable
            onPress={() => setFullscreen(false)}
            style={{ position: 'absolute', top: 60, right: 20, zIndex: 10, padding: Spacing.sm }}
          >
            <Icon name="close" size={28} color="#fff" />
          </Pressable>
          <Image
            source={{ uri: part.url }}
            style={{ width: screenWidth, height: screenHeight * 0.7 }}
            contentFit="contain"
            cachePolicy="disk"
          />
        </View>
      </Modal>
    </>
  );
}
