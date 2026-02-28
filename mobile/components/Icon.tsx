import Ionicons from '@expo/vector-icons/Ionicons';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import Feather from '@expo/vector-icons/Feather';

/**
 * Centralized icon component. When we move to dev builds,
 * swap internals to expo-image SF Symbols without changing call sites.
 */

type IconName =
  | 'gearshape'
  | 'arrow-up'
  | 'paperclip'
  | 'chat-fill'
  | 'stethoscope'
  | 'chevron-down'
  | 'chevron-right'
  | 'heart-clipboard'
  | 'plus'
  | 'people'
  | 'doc-search'
  | 'chat-bubbles';

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
  }
}
