import Ionicons from '@expo/vector-icons/Ionicons';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import Feather from '@expo/vector-icons/Feather';

/**
 * Centralized icon component. When we move to dev builds,
 * swap internals to expo-image SF Symbols without changing call sites.
 */

export type IconName =
  | 'gearshape'
  | 'arrow-up'
  | 'paperclip'
  | 'chat-fill'
  | 'stethoscope'
  | 'chevron-down'
  | 'chevron-up'
  | 'chevron-right'
  | 'heart-clipboard'
  | 'plus'
  | 'people'
  | 'doc-search'
  | 'chat-bubbles'
  | 'menu'
  | 'pen-square'
  | 'camera'
  | 'image'
  | 'document'
  | 'close'
  | 'checkmark-circle'
  | 'close-circle'
  | 'brain';

interface Props {
  name: IconName;
  size: number;
  color: string;
}

export function Icon({ name, size, color }: Props) {
  switch (name) {
    case 'gearshape':
      return <Ionicons name="settings-outline" size={size} color={color} />;
    case 'arrow-up':
      return <Feather name="arrow-up" size={size} color={color} />;
    case 'paperclip':
      return <Feather name="paperclip" size={size} color={color} />;
    case 'chat-fill':
      return <Ionicons name="chatbubble" size={size} color={color} />;
    case 'stethoscope':
      return <MaterialCommunityIcons name="stethoscope" size={size} color={color} />;
    case 'chevron-down':
      return <Ionicons name="chevron-down" size={size} color={color} />;
    case 'chevron-right':
      return <Ionicons name="chevron-forward" size={size} color={color} />;
    case 'heart-clipboard':
      return <Ionicons name="heart" size={size} color={color} />;
    case 'plus':
      return <Ionicons name="add" size={size} color={color} />;
    case 'people':
      return <Ionicons name="people" size={size} color={color} />;
    case 'doc-search':
      return <Ionicons name="document-text-outline" size={size} color={color} />;
    case 'chat-bubbles':
      return <Ionicons name="chatbubbles-outline" size={size} color={color} />;
    case 'menu':
      return <Ionicons name="menu-outline" size={size} color={color} />;
    case 'pen-square':
      return <Ionicons name="create-outline" size={size} color={color} />;
    case 'camera':
      return <Ionicons name="camera-outline" size={size} color={color} />;
    case 'image':
      return <Ionicons name="image-outline" size={size} color={color} />;
    case 'document':
      return <Ionicons name="document-outline" size={size} color={color} />;
    case 'close':
      return <Ionicons name="close" size={size} color={color} />;
    case 'chevron-up':
      return <Ionicons name="chevron-up" size={size} color={color} />;
    case 'checkmark-circle':
      return <Ionicons name="checkmark-circle" size={size} color={color} />;
    case 'close-circle':
      return <Ionicons name="close-circle" size={size} color={color} />;
    case 'brain':
      return <MaterialCommunityIcons name="brain" size={size} color={color} />;
  }
}
