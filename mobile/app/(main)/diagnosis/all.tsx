import { SessionListScreen } from '@/components/SessionListScreen';
import { useDiagnosisSessions } from '@/hooks/useDiagnosis';

export default function AllSessionsScreen() {
  return (
    <SessionListScreen
      config={{
        type: 'diagnosis',
        screenTitle: 'Sessions',
        emptyIcon: 'stethoscope',
        emptyText: 'No sessions yet',
        emptyAction: 'Start a diagnosis',
        useData: useDiagnosisSessions,
        getTitle: (s) => s.title || s.chief_complaint,
        getId: (s) => s.id,
        getRoute: () => '/(main)/diagnosis/[sid]',
        paramName: 'sid',
      }}
    />
  );
}
