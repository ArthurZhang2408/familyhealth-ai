import { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  ScrollView,
  Alert,
  LayoutAnimation,
  Keyboard,
  type TextInput as TextInputType,
} from 'react-native';
import { useRouter, useLocalSearchParams, Stack } from 'expo-router';
import { useCreateProfile, useProfile, useUpdateProfile } from '@/hooks/useProfiles';
import { useProfileStore } from '@/stores/profile';
import { useColors } from '@/hooks/useColors';
import { useShadow } from '@/hooks/useShadow';
import { useHapticPress } from '@/hooks/useHapticPress';
import { Icon } from '@/components/Icon';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Spacing, FontSize, FontWeight, BorderRadius } from '@/constants/theme';
import type {
  Relationship,
  Sex,
  BloodType,
  SmokingStatus,
  AlcoholFrequency,
  SurgicalProcedure,
  ProfileCreate,
  ProfileUpdate,
  Allergy,
  Medication,
} from '@/types/api';

// ── Constants ───────────────────────────────────────────────────────────────

const TOTAL_STEPS = 5;

type RelCategory = 'self' | 'parent' | 'spouse' | 'child' | 'sibling' | 'grandparent' | 'other';

const REL_CATEGORIES: { value: RelCategory; label: string }[] = [
  { value: 'self', label: 'Myself' },
  { value: 'parent', label: 'Parent' },
  { value: 'child', label: 'Child' },
  { value: 'spouse', label: 'Spouse' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'grandparent', label: 'Grandparent' },
  { value: 'other', label: 'Other' },
];

const REL_SUB_OPTIONS: Partial<Record<RelCategory, { value: Relationship; label: string }[]>> = {
  parent: [
    { value: 'father', label: 'Father' },
    { value: 'mother', label: 'Mother' },
    { value: 'parent', label: 'Other/Unspecified' },
  ],
  child: [
    { value: 'son', label: 'Son' },
    { value: 'daughter', label: 'Daughter' },
    { value: 'child', label: 'Other/Unspecified' },
  ],
  sibling: [
    { value: 'brother', label: 'Brother' },
    { value: 'sister', label: 'Sister' },
    { value: 'sibling', label: 'Other/Unspecified' },
  ],
  grandparent: [
    { value: 'grandfather', label: 'Grandfather' },
    { value: 'grandmother', label: 'Grandmother' },
    { value: 'grandparent', label: 'Other/Unspecified' },
  ],
};

/** Map any specific relationship to its category color key. */
function relColorKey(rel: Relationship): string {
  const map: Record<string, string> = {
    self: 'relationshipSelf',
    parent: 'relationshipParent', father: 'relationshipParent', mother: 'relationshipParent',
    spouse: 'relationshipSpouse',
    child: 'relationshipChild', son: 'relationshipChild', daughter: 'relationshipChild',
    sibling: 'relationshipSibling', brother: 'relationshipSibling', sister: 'relationshipSibling',
    grandparent: 'relationshipOther', grandfather: 'relationshipOther', grandmother: 'relationshipOther',
    other: 'relationshipOther',
  };
  return map[rel] || 'relationshipOther';
}

const SEXES: { value: Sex; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

const BLOOD_GROUPS = ['A', 'B', 'AB', 'O'] as const;
const RH_OPTIONS = ['+', '-'] as const;

const MED_FREQUENCIES = ['daily', 'twice daily', 'as needed', 'weekly'] as const;

const ALLERGY_SEVERITIES = ['Mild', 'Moderate', 'Severe'] as const;

const COMMON_CONDITIONS = [
  'Diabetes',
  'High blood pressure',
  'Asthma/COPD',
  'Heart disease',
  'High cholesterol',
  'Thyroid disorder',
  'Anxiety/Depression',
  'Arthritis',
  'Cancer',
  'Kidney disease',
] as const;

const CONDITION_STATUSES = ['Active', 'Managed', 'Resolved'] as const;

const SMOKING_OPTIONS: { value: SmokingStatus; label: string }[] = [
  { value: 'never', label: 'Never' },
  { value: 'former', label: 'Former' },
  { value: 'current', label: 'Current' },
];

const ALCOHOL_OPTIONS: { value: AlcoholFrequency; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'occasional', label: 'Occasional' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'heavy', label: 'Heavy' },
];

const FAMILY_CONDITIONS = [
  'Heart disease',
  'Diabetes',
  'Cancer',
  'Stroke',
  'High blood pressure',
  'Mental illness',
] as const;

const FAMILY_MEMBERS = [
  'Father', 'Mother', 'Brother', 'Sister', 'Grandfather', 'Grandmother',
] as const;

/** Validate and format DOB fields into YYYY-MM-DD, or null if incomplete/invalid. */
function parseDob(month: string, day: string, year: string): string | null {
  if (!month || !day || !year || year.length !== 4) return null;
  const m = parseInt(month, 10);
  const d = parseInt(day, 10);
  const y = parseInt(year, 10);
  const now = new Date();
  if (m < 1 || m > 12 || d < 1 || d > 31 || y < 1900 || y > now.getFullYear()) return null;
  // Validate the actual date (handles Feb 30, etc.)
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return null;
  if (date > now) return null;
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

// ── Main Screen ─────────────────────────────────────────────────────────────

export default function NewProfileScreen() {
  const Colors = useColors();
  const Shadow = useShadow();
  const router = useRouter();
  const { pid } = useLocalSearchParams<{ pid?: string }>();
  const isEdit = !!pid;

  const createProfile = useCreateProfile();
  const setActiveProfile = useProfileStore((s) => s.setActiveProfile);
  const { data: profile, isLoading: profileLoading } = useProfile(pid ?? '');
  const updateProfile = useUpdateProfile(pid ?? '');

  const [step, setStep] = useState(0);
  const [populated, setPopulated] = useState(false);
  // Step 0 state
  const [name, setName] = useState('');
  const [relCat, setRelCat] = useState<RelCategory>('self');
  const [relationship, setRelationship] = useState<Relationship>('self');

  // Step 1 state
  const [dobMonth, setDobMonth] = useState('');
  const [dobDay, setDobDay] = useState('');
  const [dobYear, setDobYear] = useState('');
  const [sex, setSex] = useState<Sex | null>(null);
  const [bloodType, setBloodType] = useState<BloodType | null>(null);
  const dayRef = useRef<TextInputType>(null);
  const yearRef = useRef<TextInputType>(null);

  // Step 2 state (body & lifestyle)
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [smokingStatus, setSmokingStatus] = useState<SmokingStatus | null>(null);
  const [alcoholFrequency, setAlcoholFrequency] = useState<AlcoholFrequency | null>(null);
  const [isPregnant, setIsPregnant] = useState<boolean | null>(null);

  // Step 3 state (meds & allergies)
  const [medications, setMedications] = useState<Medication[]>([]);
  const [allergies, setAllergies] = useState<Allergy[]>([]);
  const [showMedEntry, setShowMedEntry] = useState(false);
  const [showAllergyEntry, setShowAllergyEntry] = useState(false);
  const [noMeds, setNoMeds] = useState(false);
  const [noAllergies, setNoAllergies] = useState(false);
  const [medName, setMedName] = useState('');
  const [medDosage, setMedDosage] = useState('');
  const [medFrequency, setMedFrequency] = useState('');
  const [allergyName, setAllergyName] = useState('');
  const [allergySeverity, setAllergySeverity] = useState('');
  const [allergyReaction, setAllergyReaction] = useState('');

  // Step 4 state (conditions, surgical history, family history)
  const [selectedConditions, setSelectedConditions] = useState<
    Map<string, string>
  >(new Map());
  const [showCustomEntry, setShowCustomEntry] = useState(false);
  const [customCondition, setCustomCondition] = useState('');
  const [surgicalHistory, setSurgicalHistory] = useState<SurgicalProcedure[]>([]);
  const [showSurgeryEntry, setShowSurgeryEntry] = useState(false);
  const [surgeryName, setSurgeryName] = useState('');
  const [surgeryYear, setSurgeryYear] = useState('');
  const [familyHistory, setFamilyHistory] = useState<Record<string, string[]>>({});

  // ── Pre-populate state in edit mode ────────────────────────────────────
  useEffect(() => {
    if (!isEdit || !profile || populated) return;
    setName(profile.name);
    setRelationship(profile.relationship);
    // Derive relCat from relationship
    const catMap: Record<string, RelCategory> = {
      self: 'self', parent: 'parent', father: 'parent', mother: 'parent',
      spouse: 'spouse', child: 'child', son: 'child', daughter: 'child',
      sibling: 'sibling', brother: 'sibling', sister: 'sibling',
      grandparent: 'grandparent', grandfather: 'grandparent', grandmother: 'grandparent',
      other: 'other',
    };
    setRelCat(catMap[profile.relationship] || 'other');
    if (profile.date_of_birth) {
      const [y, m, d] = profile.date_of_birth.split('-');
      setDobYear(y);
      setDobMonth(String(parseInt(m)));
      setDobDay(String(parseInt(d)));
    }
    if (profile.sex) setSex(profile.sex);
    if (profile.blood_type) setBloodType(profile.blood_type as BloodType);
    if (profile.height_cm) setHeightCm(String(profile.height_cm));
    if (profile.weight_kg) setWeightKg(String(profile.weight_kg));
    if (profile.smoking_status) setSmokingStatus(profile.smoking_status as SmokingStatus);
    if (profile.alcohol_frequency) setAlcoholFrequency(profile.alcohol_frequency as AlcoholFrequency);
    if (profile.is_pregnant != null) setIsPregnant(profile.is_pregnant);
    if (profile.surgical_history?.length) {
      setSurgicalHistory(profile.surgical_history.map(s => ({
        procedure: s.procedure,
        year: s.year,
      })));
    }
    if (profile.family_history && Object.keys(profile.family_history).length > 0) {
      setFamilyHistory(profile.family_history);
    }
    if (profile.medications?.length) {
      setMedications(profile.medications.map(m => ({
        name: m.name,
        dosage: m.dosage,
        frequency: m.frequency,
      })));
    }
    if (profile.allergies?.length) {
      setAllergies(profile.allergies.map(a => ({
        name: a.name,
        severity: a.severity,
        reaction: a.reaction,
      })));
    }
    if (profile.medical_conditions?.length) {
      const map = new Map<string, string>();
      profile.medical_conditions.forEach(c => {
        map.set(c.name, c.status || 'Active');
      });
      setSelectedConditions(map);
    }
    setPopulated(true);
  }, [isEdit, profile, populated]);

  const animateLayout = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
  }, []);

  // ── Navigation ──────────────────────────────────────────────────────────

  const goNext = useCallback(() => {
    Keyboard.dismiss();
    if (step === 0 && !name.trim()) {
      Alert.alert('Name required', 'Please enter a name for this profile.');
      return;
    }
    animateLayout();
    setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  }, [step, name, animateLayout]);

  const goBack = useCallback(() => {
    Keyboard.dismiss();
    if (step === 0) {
      router.back();
    } else {
      animateLayout();
      setStep((s) => s - 1);
    }
  }, [step, router, animateLayout]);

  const handleCreate = useCallback(async () => {
    // Backend accepts frontend-friendly field names (name, medications, etc.)
    // via validation aliases — no manual transforms needed.

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const payload: Record<string, any> = {
      name: name.trim(),
      relationship,
    };

    // Step 1: basics
    if (step >= 1) {
      const dob = parseDob(dobMonth, dobDay, dobYear);
      if (dob) payload.date_of_birth = dob;
      if (sex) payload.sex = sex;
      if (bloodType) payload.blood_type = bloodType;
    }

    // Step 2: body & lifestyle
    if (step >= 2) {
      const h = parseFloat(heightCm);
      const w = parseFloat(weightKg);
      if (!isNaN(h) && h > 0) payload.height_cm = h;
      if (!isNaN(w) && w > 0) payload.weight_kg = w;
      if (smokingStatus) payload.smoking_status = smokingStatus;
      if (alcoholFrequency) payload.alcohol_frequency = alcoholFrequency;
      if (isPregnant != null) payload.is_pregnant = isPregnant;
    }

    // Step 3: meds & allergies
    if (step >= 3) {
      if (medications.length > 0) {
        payload.medications = medications.map((m) => ({
          name: m.name,
          dosage: m.dosage || 'as prescribed',
          frequency: m.frequency || 'as directed',
        }));
      }
      if (allergies.length > 0) {
        payload.allergies = allergies.map((a) => ({
          name: a.name,
          severity: a.severity.toLowerCase(),
          reaction: a.reaction || null,
        }));
      }
    }

    // Step 4: conditions, surgical history, family history
    if (step >= 4) {
      if (selectedConditions.size > 0) {
        payload.medical_conditions = Array.from(selectedConditions.entries()).map(
          ([condName, status]) => ({
            name: condName,
            status: status.toLowerCase(),
          }),
        );
      }
      if (surgicalHistory.length > 0) {
        payload.surgical_history = surgicalHistory;
      }
      const nonEmptyFH = Object.fromEntries(
        Object.entries(familyHistory).filter(([, members]) => members.length > 0),
      );
      if (Object.keys(nonEmptyFH).length > 0) {
        payload.family_history = nonEmptyFH;
      }
    }

    try {
      if (isEdit) {
        await updateProfile.mutateAsync(payload as ProfileUpdate);
        router.back();
      } else {
        const created = await createProfile.mutateAsync(payload as ProfileCreate);
        setActiveProfile(created);
        // Dismiss this modal, then go home so we don't land on a stale
        // conversation screen from a different profile.
        router.dismiss();
        router.navigate('/(main)' as never);
      }
    } catch (err: unknown) {
      Alert.alert('Error', err instanceof Error ? err.message : isEdit ? 'Could not update profile.' : 'Could not create profile.');
    }
  }, [selectedConditions, name, relationship, dobMonth, dobDay, dobYear, sex, bloodType, heightCm, weightKg, smokingStatus, alcoholFrequency, isPregnant, medications, allergies, surgicalHistory, familyHistory, step, createProfile, updateProfile, isEdit, router, setActiveProfile]);

  const handleSkipCreate = useCallback(async () => {
    // Save whatever we have so far and create
    await handleCreate();
  }, [handleCreate]);

  const onBackPress = useHapticPress(goBack);

  const isSaving = isEdit ? updateProfile.isPending : createProfile.isPending;

  // ── Relationship color ──────────────────────────────────────────────────

  const relColor = Colors[relColorKey(relationship) as keyof typeof Colors];

  // ── Render ──────────────────────────────────────────────────────────────

  if (isEdit && profileLoading) return <LoadingSpinner />;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: Colors.surface }}
      contentContainerStyle={{ flexGrow: 1, padding: Spacing.lg, paddingBottom: Spacing.xxl * 2 }}
      keyboardShouldPersistTaps="handled"
    >
      <Stack.Screen options={{
        headerTitle: isEdit ? 'Edit Profile' : 'New Profile',
        headerLeft: () => (
          <Pressable onPress={onBackPress} hitSlop={12}>
            <Text style={{ fontSize: FontSize.md, color: Colors.primary }}>
              {step === 0 ? 'Cancel' : 'Back'}
            </Text>
          </Pressable>
        ),
      }} />

      {/* Step dots */}
      <StepDots current={step} total={TOTAL_STEPS} />

      {step === 0 && (
        <Step0Identity
          name={name}
          setName={setName}
          relCat={relCat}
          setRelCat={setRelCat}
          relationship={relationship}
          setRelationship={setRelationship}
          relColor={relColor}
          onContinue={goNext}
          animateLayout={animateLayout}
        />
      )}

      {step === 1 && (
        <Step1Basics
          dobMonth={dobMonth}
          setDobMonth={setDobMonth}
          dobDay={dobDay}
          setDobDay={setDobDay}
          dobYear={dobYear}
          setDobYear={setDobYear}
          dayRef={dayRef}
          yearRef={yearRef}
          sex={sex}
          setSex={setSex}
          bloodType={bloodType}
          setBloodType={setBloodType}
          onContinue={goNext}
          onSkip={isEdit ? undefined : goNext}
        />
      )}

      {step === 2 && (
        <Step2BodyLifestyle
          heightCm={heightCm}
          setHeightCm={setHeightCm}
          weightKg={weightKg}
          setWeightKg={setWeightKg}
          smokingStatus={smokingStatus}
          setSmokingStatus={setSmokingStatus}
          alcoholFrequency={alcoholFrequency}
          setAlcoholFrequency={setAlcoholFrequency}
          isPregnant={isPregnant}
          setIsPregnant={setIsPregnant}
          sex={sex}
          onContinue={goNext}
          onSkip={isEdit ? undefined : goNext}
        />
      )}

      {step === 3 && (
        <Step3MedsAllergies
          medications={medications}
          setMedications={setMedications}
          allergies={allergies}
          setAllergies={setAllergies}
          showMedEntry={showMedEntry}
          setShowMedEntry={setShowMedEntry}
          showAllergyEntry={showAllergyEntry}
          setShowAllergyEntry={setShowAllergyEntry}
          noMeds={noMeds}
          setNoMeds={setNoMeds}
          noAllergies={noAllergies}
          setNoAllergies={setNoAllergies}
          medName={medName}
          setMedName={setMedName}
          medDosage={medDosage}
          setMedDosage={setMedDosage}
          medFrequency={medFrequency}
          setMedFrequency={setMedFrequency}
          allergyName={allergyName}
          setAllergyName={setAllergyName}
          allergySeverity={allergySeverity}
          setAllergySeverity={setAllergySeverity}
          allergyReaction={allergyReaction}
          setAllergyReaction={setAllergyReaction}
          onContinue={goNext}
          onSkip={isEdit ? undefined : goNext}
          animateLayout={animateLayout}
        />
      )}

      {step === 4 && (
        <Step4Conditions
          selectedConditions={selectedConditions}
          setSelectedConditions={setSelectedConditions}
          showCustomEntry={showCustomEntry}
          setShowCustomEntry={setShowCustomEntry}
          customCondition={customCondition}
          setCustomCondition={setCustomCondition}
          surgicalHistory={surgicalHistory}
          setSurgicalHistory={setSurgicalHistory}
          showSurgeryEntry={showSurgeryEntry}
          setShowSurgeryEntry={setShowSurgeryEntry}
          surgeryName={surgeryName}
          setSurgeryName={setSurgeryName}
          surgeryYear={surgeryYear}
          setSurgeryYear={setSurgeryYear}
          familyHistory={familyHistory}
          setFamilyHistory={setFamilyHistory}
          onCreateProfile={handleCreate}
          onSkip={isEdit ? undefined : handleSkipCreate}
          isPending={isSaving}
          animateLayout={animateLayout}
          submitLabel={isEdit ? 'Save changes' : undefined}
        />
      )}
    </ScrollView>
  );
}

// ── Step Dots ───────────────────────────────────────────────────────────────

const STEP_LABELS = ['Identity', 'Basics', 'Lifestyle', 'Meds', 'Conditions'];

function StepDots({ current, total }: { current: number; total: number }) {
  const Colors = useColors();
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'center',
        gap: Spacing.sm,
        marginBottom: Spacing.lg,
        alignItems: 'center',
      }}
    >
      {Array.from({ length: total }, (_, i) => (
        <View key={i} style={{ alignItems: 'center', gap: 4 }}>
          <View
            style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              backgroundColor: i === current ? Colors.primary : Colors.border,
            }}
          />
          <Text
            style={{
              fontSize: 10,
              color: i === current ? Colors.primary : Colors.textMuted,
              fontWeight: i === current ? FontWeight.semibold : FontWeight.regular,
            }}
          >
            {STEP_LABELS[i] ?? ''}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ── Shared Sub-components ───────────────────────────────────────────────────

function Pill({
  label,
  selected,
  onPress,
  small,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  small?: boolean;
}) {
  const Colors = useColors();
  const wrappedPress = useHapticPress(onPress);
  return (
    <Pressable
      onPress={wrappedPress}
      style={{
        paddingHorizontal: small ? Spacing.sm + 2 : Spacing.md,
        paddingVertical: small ? Spacing.xs + 2 : Spacing.sm,
        borderRadius: BorderRadius.full,
        borderCurve: 'continuous',
        backgroundColor: selected ? Colors.primary : Colors.surface,
        borderWidth: 1,
        borderColor: selected ? Colors.primary : Colors.border,
      }}
    >
      <Text
        style={{
          fontSize: small ? FontSize.xs : FontSize.sm,
          fontWeight: FontWeight.medium,
          color: selected ? Colors.textInverse : Colors.text,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function PrimaryButton({
  label,
  onPress,
  disabled,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const Colors = useColors();
  const Shadow = useShadow();
  const wrappedPress = useHapticPress(onPress);
  return (
    <Pressable
      onPress={wrappedPress}
      disabled={disabled}
      style={({ pressed }) => ({
        backgroundColor: disabled ? Colors.primaryLight : Colors.primary,
        borderRadius: BorderRadius.md,
        borderCurve: 'continuous',
        padding: Spacing.md,
        alignItems: 'center' as const,
        opacity: pressed ? 0.9 : 1,
        ...Shadow.sm,
      })}
    >
      <Text
        style={{
          fontSize: FontSize.md,
          fontWeight: FontWeight.semibold,
          color: Colors.textInverse,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function SkipButton({ onPress }: { onPress: () => void }) {
  const Colors = useColors();
  const wrappedPress = useHapticPress(onPress);
  return (
    <Pressable
      onPress={wrappedPress}
      style={({ pressed }) => ({
        padding: Spacing.md,
        alignItems: 'center' as const,
        opacity: pressed ? 0.7 : 1,
      })}
    >
      <Text
        style={{
          fontSize: FontSize.sm,
          fontWeight: FontWeight.medium,
          color: Colors.textSecondary,
        }}
      >
        Skip for now
      </Text>
    </Pressable>
  );
}

function SectionLabel({ text }: { text: string }) {
  const Colors = useColors();
  return (
    <Text
      style={{
        fontSize: FontSize.sm,
        fontWeight: FontWeight.medium,
        color: Colors.text,
      }}
    >
      {text}
    </Text>
  );
}

function HelperText({ text }: { text: string }) {
  const Colors = useColors();
  return (
    <Text
      style={{
        fontSize: FontSize.xs,
        color: Colors.textMuted,
      }}
    >
      {text}
    </Text>
  );
}

function TagChip({
  label,
  color,
  onRemove,
}: {
  label: string;
  color?: string;
  onRemove: () => void;
}) {
  const Colors = useColors();
  const bg = color || Colors.primaryLight;
  const textColor = color ? Colors.textInverse : Colors.primary;
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: bg,
        borderRadius: BorderRadius.full,
        paddingHorizontal: Spacing.sm + 2,
        paddingVertical: Spacing.xs,
        gap: Spacing.xs,
      }}
    >
      <Text style={{ fontSize: FontSize.sm, color: textColor, fontWeight: FontWeight.medium }}>
        {label}
      </Text>
      <Pressable onPress={onRemove} hitSlop={8}>
        <Icon name="close" size={14} color={textColor} />
      </Pressable>
    </View>
  );
}

function FormInput({
  value,
  onChangeText,
  placeholder,
  autoFocus,
  inputRef,
  keyboardType,
  maxLength,
  onSubmitEditing,
  returnKeyType,
}: {
  value: string;
  onChangeText: (t: string) => void;
  placeholder: string;
  autoFocus?: boolean;
  inputRef?: React.RefObject<TextInputType | null>;
  keyboardType?: 'default' | 'number-pad' | 'numeric';
  maxLength?: number;
  onSubmitEditing?: () => void;
  returnKeyType?: 'next' | 'done' | 'default';
}) {
  const Colors = useColors();
  return (
    <TextInput
      ref={inputRef}
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={Colors.textMuted}
      autoFocus={autoFocus}
      keyboardType={keyboardType}
      maxLength={maxLength}
      onSubmitEditing={onSubmitEditing}
      returnKeyType={returnKeyType}
      style={{
        backgroundColor: Colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: Colors.border,
        borderRadius: BorderRadius.md,
        borderCurve: 'continuous',
        padding: Spacing.md,
        fontSize: FontSize.md,
        color: Colors.text,
      }}
    />
  );
}

function BloodTypePicker({
  bloodType,
  setBloodType,
}: {
  bloodType: BloodType | null;
  setBloodType: (b: BloodType | null) => void;
}) {
  const Colors = useColors();

  // Derive current group and rh from bloodType
  const currentGroup = bloodType ? bloodType.replace(/[+-]$/, '') : null;
  const currentRh = bloodType?.endsWith('+') ? '+' : bloodType?.endsWith('-') ? '-' : null;

  const handleGroupPick = (group: string) => {
    if (currentGroup === group) {
      // Deselect
      setBloodType(null);
    } else {
      // Select group without Rh (e.g. "A")
      setBloodType(group as BloodType);
    }
  };

  const handleRhPick = (rh: string) => {
    if (!currentGroup) return;
    if (currentRh === rh) {
      // Deselect Rh, keep just the group
      setBloodType(currentGroup as BloodType);
    } else {
      setBloodType(`${currentGroup}${rh}` as BloodType);
    }
  };

  return (
    <View style={{ gap: Spacing.xs }}>
      <SectionLabel text="Blood type" />
      <HelperText text="Optional — skip if unsure" />
      <View style={{ flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.xs }}>
        {BLOOD_GROUPS.map((g) => (
          <Pill
            key={g}
            label={g}
            selected={currentGroup === g}
            onPress={() => handleGroupPick(g)}
          />
        ))}
      </View>
      {currentGroup && (
        <View style={{ gap: Spacing.xs, marginTop: Spacing.xs }}>
          <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>
            Rh factor (+ or -)
          </Text>
          <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
            {RH_OPTIONS.map((rh) => (
              <Pill
                key={rh}
                label={rh}
                selected={currentRh === rh}
                onPress={() => handleRhPick(rh)}
                small
              />
            ))}
            <Pill
              label="Don't know"
              selected={currentRh === null}
              onPress={() => setBloodType(currentGroup as BloodType)}
              small
            />
          </View>
        </View>
      )}
    </View>
  );
}

// ── Step 0: Identity ────────────────────────────────────────────────────────

function Step0Identity({
  name,
  setName,
  relCat,
  setRelCat,
  relationship,
  setRelationship,
  relColor,
  onContinue,
  animateLayout,
}: {
  name: string;
  setName: (s: string) => void;
  relCat: RelCategory;
  setRelCat: (c: RelCategory) => void;
  relationship: Relationship;
  setRelationship: (r: Relationship) => void;
  relColor: string;
  onContinue: () => void;
  animateLayout: () => void;
}) {
  const Colors = useColors();
  const initial = name.trim() ? name.trim()[0].toUpperCase() : '?';

  const handleCategoryPick = (cat: RelCategory) => {
    animateLayout();
    setRelCat(cat);
    const subs = REL_SUB_OPTIONS[cat];
    if (subs) {
      // Default to the first specific option (e.g. "Father" for parent)
      setRelationship(subs[0].value);
    } else {
      // Categories without sub-options (self, spouse, other)
      setRelationship(cat as Relationship);
    }
  };

  const handleSubPick = (value: Relationship) => {
    setRelationship(value);
  };

  const subOptions = REL_SUB_OPTIONS[relCat];

  return (
    <View style={{ gap: Spacing.lg }}>
      {/* Avatar */}
      <View style={{ alignItems: 'center', marginBottom: Spacing.sm }}>
        <View
          style={{
            width: 80,
            height: 80,
            borderRadius: 40,
            backgroundColor: relColor,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text
            style={{
              fontSize: FontSize.xxxl,
              fontWeight: FontWeight.bold,
              color: Colors.textInverse,
            }}
          >
            {initial}
          </Text>
        </View>
      </View>

      <Text
        style={{
          fontSize: FontSize.xl,
          fontWeight: FontWeight.bold,
          color: Colors.text,
          textAlign: 'center',
        }}
      >
        Who is this profile for?
      </Text>

      {/* Name */}
      <View style={{ gap: Spacing.xs }}>
        <SectionLabel text="Name" />
        <FormInput
          value={name}
          onChangeText={setName}
          placeholder="Full name"
          autoFocus
        />
      </View>

      {/* Relationship — two-tier picker */}
      <View style={{ gap: Spacing.sm }}>
        <SectionLabel text="Relationship" />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
          {REL_CATEGORIES.map((r) => (
            <Pill
              key={r.value}
              label={r.label}
              selected={relCat === r.value}
              onPress={() => handleCategoryPick(r.value)}
            />
          ))}
        </View>
        {subOptions && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
            {subOptions.map((s) => (
              <Pill
                key={s.value}
                label={s.label}
                selected={relationship === s.value}
                onPress={() => handleSubPick(s.value)}
                small
              />
            ))}
          </View>
        )}
      </View>

      <PrimaryButton label="Continue" onPress={onContinue} />
    </View>
  );
}

// ── Step 1: Basics ──────────────────────────────────────────────────────────

function Step1Basics({
  dobMonth,
  setDobMonth,
  dobDay,
  setDobDay,
  dobYear,
  setDobYear,
  dayRef,
  yearRef,
  sex,
  setSex,
  bloodType,
  setBloodType,
  onContinue,
  onSkip,
}: {
  dobMonth: string;
  setDobMonth: (s: string) => void;
  dobDay: string;
  setDobDay: (s: string) => void;
  dobYear: string;
  setDobYear: (s: string) => void;
  dayRef: React.RefObject<TextInputType | null>;
  yearRef: React.RefObject<TextInputType | null>;
  sex: Sex | null;
  setSex: (s: Sex) => void;
  bloodType: BloodType | null;
  setBloodType: (b: BloodType | null) => void;
  onContinue: () => void;
  onSkip?: () => void;
}) {
  const Colors = useColors();

  const handleMonthChange = (t: string) => {
    const cleaned = t.replace(/\D/g, '');
    setDobMonth(cleaned);
    if (cleaned.length === 2) dayRef.current?.focus();
  };

  const handleDayChange = (t: string) => {
    const cleaned = t.replace(/\D/g, '');
    setDobDay(cleaned);
    if (cleaned.length === 2) yearRef.current?.focus();
  };

  const handleYearChange = (t: string) => {
    setDobYear(t.replace(/\D/g, ''));
  };

  return (
    <View style={{ gap: Spacing.lg }}>
      <View>
        <Text
          style={{
            fontSize: FontSize.xl,
            fontWeight: FontWeight.bold,
            color: Colors.text,
            textAlign: 'center',
          }}
        >
          Basic details
        </Text>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.xs,
          }}
        >
          Helps personalize every health assessment
        </Text>
      </View>

      {/* Date of birth */}
      <View style={{ gap: Spacing.xs }}>
        <SectionLabel text="Date of birth" />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: Spacing.sm }}>
          <TextInput
            value={dobMonth}
            onChangeText={handleMonthChange}
            placeholder="MM"
            placeholderTextColor={Colors.textMuted}
            keyboardType="number-pad"
            maxLength={2}
            style={{
              flex: 1,
              backgroundColor: Colors.surfaceSecondary,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
              textAlign: 'center',
            }}
          />
          <Text style={{ fontSize: FontSize.lg, color: Colors.textMuted }}>/</Text>
          <TextInput
            ref={dayRef}
            value={dobDay}
            onChangeText={handleDayChange}
            placeholder="DD"
            placeholderTextColor={Colors.textMuted}
            keyboardType="number-pad"
            maxLength={2}
            style={{
              flex: 1,
              backgroundColor: Colors.surfaceSecondary,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
              textAlign: 'center',
            }}
          />
          <Text style={{ fontSize: FontSize.lg, color: Colors.textMuted }}>/</Text>
          <TextInput
            ref={yearRef}
            value={dobYear}
            onChangeText={handleYearChange}
            placeholder="YYYY"
            placeholderTextColor={Colors.textMuted}
            keyboardType="number-pad"
            maxLength={4}
            style={{
              flex: 1.5,
              backgroundColor: Colors.surfaceSecondary,
              borderWidth: 1,
              borderColor: Colors.border,
              borderRadius: BorderRadius.md,
              borderCurve: 'continuous',
              padding: Spacing.md,
              fontSize: FontSize.md,
              color: Colors.text,
              textAlign: 'center',
            }}
          />
        </View>
        {dobMonth && dobDay && dobYear && (
          dobYear.length < 4 ? (
            <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, marginTop: Spacing.xs }}>
              Enter 4-digit year
            </Text>
          ) : !parseDob(dobMonth, dobDay, dobYear) ? (
            <Text style={{ fontSize: FontSize.xs, color: Colors.error, marginTop: Spacing.xs }}>
              Please enter a valid date
            </Text>
          ) : null
        )}
      </View>

      {/* Biological sex */}
      <View style={{ gap: Spacing.sm }}>
        <SectionLabel text="Biological sex" />
        <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
          {SEXES.map((s) => (
            <Pill
              key={s.value}
              label={s.label}
              selected={sex === s.value}
              onPress={() => setSex(s.value)}
            />
          ))}
        </View>
      </View>

      {/* Blood type — two-tier: group then Rh */}
      <BloodTypePicker bloodType={bloodType} setBloodType={setBloodType} />

      <PrimaryButton label="Continue" onPress={onContinue} />
      {onSkip && <SkipButton onPress={onSkip} />}
    </View>
  );
}

// ── Step 2: Body & Lifestyle ────────────────────────────────────────────────

function Step2BodyLifestyle({
  heightCm,
  setHeightCm,
  weightKg,
  setWeightKg,
  smokingStatus,
  setSmokingStatus,
  alcoholFrequency,
  setAlcoholFrequency,
  isPregnant,
  setIsPregnant,
  sex,
  onContinue,
  onSkip,
}: {
  heightCm: string;
  setHeightCm: (s: string) => void;
  weightKg: string;
  setWeightKg: (s: string) => void;
  smokingStatus: SmokingStatus | null;
  setSmokingStatus: (s: SmokingStatus) => void;
  alcoholFrequency: AlcoholFrequency | null;
  setAlcoholFrequency: (s: AlcoholFrequency) => void;
  isPregnant: boolean | null;
  setIsPregnant: (b: boolean) => void;
  sex: Sex | null;
  onContinue: () => void;
  onSkip?: () => void;
}) {
  const Colors = useColors();

  return (
    <View style={{ gap: Spacing.lg }}>
      <View>
        <Text
          style={{
            fontSize: FontSize.xl,
            fontWeight: FontWeight.bold,
            color: Colors.text,
            textAlign: 'center',
          }}
        >
          Body & Lifestyle
        </Text>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.xs,
          }}
        >
          Helps with dosing, BMI, and risk assessment
        </Text>
      </View>

      {/* Height & Weight */}
      <View style={{ flexDirection: 'row', gap: Spacing.md }}>
        <View style={{ flex: 1, gap: Spacing.xs }}>
          <SectionLabel text="Height (cm)" />
          <FormInput
            value={heightCm}
            onChangeText={(t) => setHeightCm(t.replace(/[^0-9.]/g, ''))}
            placeholder="e.g. 170"
            keyboardType="numeric"
          />
        </View>
        <View style={{ flex: 1, gap: Spacing.xs }}>
          <SectionLabel text="Weight (kg)" />
          <FormInput
            value={weightKg}
            onChangeText={(t) => setWeightKg(t.replace(/[^0-9.]/g, ''))}
            placeholder="e.g. 70"
            keyboardType="numeric"
          />
        </View>
      </View>

      {/* Smoking */}
      <View style={{ gap: Spacing.sm }}>
        <SectionLabel text="Smoking" />
        <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
          {SMOKING_OPTIONS.map((o) => (
            <Pill
              key={o.value}
              label={o.label}
              selected={smokingStatus === o.value}
              onPress={() => setSmokingStatus(o.value)}
            />
          ))}
        </View>
      </View>

      {/* Alcohol */}
      <View style={{ gap: Spacing.sm }}>
        <SectionLabel text="Alcohol" />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
          {ALCOHOL_OPTIONS.map((o) => (
            <Pill
              key={o.value}
              label={o.label}
              selected={alcoholFrequency === o.value}
              onPress={() => setAlcoholFrequency(o.value)}
            />
          ))}
        </View>
      </View>

      {/* Pregnancy — only show for female */}
      {sex === 'female' && (
        <View style={{ gap: Spacing.sm }}>
          <SectionLabel text="Currently pregnant?" />
          <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
            <Pill label="Yes" selected={isPregnant === true} onPress={() => setIsPregnant(true)} />
            <Pill label="No" selected={isPregnant === false} onPress={() => setIsPregnant(false)} />
          </View>
        </View>
      )}

      <PrimaryButton label="Continue" onPress={onContinue} />
      {onSkip && <SkipButton onPress={onSkip} />}
    </View>
  );
}

// ── Step 3: Medications & Allergies ─────────────────────────────────────────

function Step3MedsAllergies({
  medications,
  setMedications,
  allergies,
  setAllergies,
  showMedEntry,
  setShowMedEntry,
  showAllergyEntry,
  setShowAllergyEntry,
  noMeds,
  setNoMeds,
  noAllergies,
  setNoAllergies,
  medName,
  setMedName,
  medDosage,
  setMedDosage,
  medFrequency,
  setMedFrequency,
  allergyName,
  setAllergyName,
  allergySeverity,
  setAllergySeverity,
  allergyReaction,
  setAllergyReaction,
  onContinue,
  onSkip,
  animateLayout,
}: {
  medications: Medication[];
  setMedications: React.Dispatch<React.SetStateAction<Medication[]>>;
  allergies: Allergy[];
  setAllergies: React.Dispatch<React.SetStateAction<Allergy[]>>;
  showMedEntry: boolean;
  setShowMedEntry: (v: boolean) => void;
  showAllergyEntry: boolean;
  setShowAllergyEntry: (v: boolean) => void;
  noMeds: boolean;
  setNoMeds: (v: boolean) => void;
  noAllergies: boolean;
  setNoAllergies: (v: boolean) => void;
  medName: string;
  setMedName: (s: string) => void;
  medDosage: string;
  setMedDosage: (s: string) => void;
  medFrequency: string;
  setMedFrequency: (s: string) => void;
  allergyName: string;
  setAllergyName: (s: string) => void;
  allergySeverity: string;
  setAllergySeverity: (s: string) => void;
  allergyReaction: string;
  setAllergyReaction: (s: string) => void;
  onContinue: () => void;
  onSkip?: () => void;
  animateLayout: () => void;
}) {
  const Colors = useColors();

  const addMed = () => {
    if (!medName.trim()) return;
    animateLayout();
    setMedications((prev) => [
      ...prev,
      {
        name: medName.trim(),
        dosage: medDosage.trim() || undefined,
        frequency: medFrequency || undefined,
      },
    ]);
    setMedName('');
    setMedDosage('');
    setMedFrequency('');
    setShowMedEntry(false);
  };

  const removeMed = (idx: number) => {
    animateLayout();
    setMedications((prev) => prev.filter((_, i) => i !== idx));
  };

  const addAllergy = () => {
    if (!allergyName.trim()) return;
    animateLayout();
    setAllergies((prev) => [
      ...prev,
      {
        name: allergyName.trim(),
        severity: allergySeverity || 'Mild',
        reaction: allergyReaction.trim() || undefined,
      },
    ]);
    setAllergyName('');
    setAllergySeverity('');
    setAllergyReaction('');
    setShowAllergyEntry(false);
  };

  const removeAllergy = (idx: number) => {
    animateLayout();
    setAllergies((prev) => prev.filter((_, i) => i !== idx));
  };

  const severityColor = (sev: string) => {
    switch (sev.toLowerCase()) {
      case 'mild':
        return Colors.success;
      case 'moderate':
        return Colors.warning;
      case 'severe':
        return Colors.error;
      default:
        return Colors.primaryLight;
    }
  };

  return (
    <View style={{ gap: Spacing.lg }}>
      <View>
        <Text
          style={{
            fontSize: FontSize.xl,
            fontWeight: FontWeight.bold,
            color: Colors.text,
            textAlign: 'center',
          }}
        >
          Medications & Allergies
        </Text>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.xs,
          }}
        >
          Helps check interactions and avoid reactions
        </Text>
      </View>

      {/* Medications section */}
      <View
        style={{
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
          padding: Spacing.md,
          gap: Spacing.sm,
        }}
      >
        <SectionLabel text="Medications" />

        {/* Existing meds as chips */}
        {medications.length > 0 && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
            {medications.map((m, i) => (
              <TagChip
                key={`${m.name}-${i}`}
                label={m.dosage ? `${m.name} (${m.dosage})` : m.name}
                onRemove={() => removeMed(i)}
              />
            ))}
          </View>
        )}

        {/* Inline entry */}
        {showMedEntry && (
          <View
            style={{
              gap: Spacing.sm,
              backgroundColor: Colors.surface,
              borderRadius: BorderRadius.sm,
              borderCurve: 'continuous',
              padding: Spacing.sm,
            }}
          >
            <FormInput
              value={medName}
              onChangeText={setMedName}
              placeholder="Medication name"
              autoFocus
            />
            <FormInput
              value={medDosage}
              onChangeText={setMedDosage}
              placeholder="Dosage (e.g. 10mg)"
            />
            <View style={{ gap: Spacing.xs }}>
              <HelperText text="Frequency" />
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
                {MED_FREQUENCIES.map((f) => (
                  <Pill
                    key={f}
                    label={f}
                    selected={medFrequency === f}
                    onPress={() => setMedFrequency(f)}
                    small
                  />
                ))}
              </View>
            </View>
            <PrimaryButton label="Add" onPress={addMed} />
          </View>
        )}

        {!noMeds && !showMedEntry && (
          <Pressable
            onPress={() => {
              animateLayout();
              setShowMedEntry(true);
              setNoMeds(false);
            }}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.xs,
              paddingVertical: Spacing.xs,
            }}
          >
            <Icon name="plus" size={18} color={Colors.primary} />
            <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.medium }}>
              Add medication
            </Text>
          </Pressable>
        )}

        {/* No meds toggle */}
        <Pressable
          onPress={() => {
            animateLayout();
            const next = !noMeds;
            setNoMeds(next);
            if (next) {
              setMedications([]);
              setShowMedEntry(false);
            }
          }}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: Spacing.sm,
            paddingVertical: Spacing.xs,
          }}
        >
          <View
            style={{
              width: 20,
              height: 20,
              borderRadius: 4,
              borderWidth: 1.5,
              borderColor: noMeds ? Colors.primary : Colors.border,
              backgroundColor: noMeds ? Colors.primary : 'transparent',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {noMeds && <Icon name="checkmark-circle" size={14} color={Colors.textInverse} />}
          </View>
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>
            No current medications
          </Text>
        </Pressable>
      </View>

      {/* Allergies section */}
      <View
        style={{
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
          padding: Spacing.md,
          gap: Spacing.sm,
        }}
      >
        <SectionLabel text="Allergies" />

        {/* Existing allergies as colored chips */}
        {allergies.length > 0 && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
            {allergies.map((a, i) => (
              <TagChip
                key={`${a.name}-${i}`}
                label={`${a.name} (${a.severity})`}
                color={severityColor(a.severity)}
                onRemove={() => removeAllergy(i)}
              />
            ))}
          </View>
        )}

        {/* Inline entry */}
        {showAllergyEntry && (
          <View
            style={{
              gap: Spacing.sm,
              backgroundColor: Colors.surface,
              borderRadius: BorderRadius.sm,
              borderCurve: 'continuous',
              padding: Spacing.sm,
            }}
          >
            <FormInput
              value={allergyName}
              onChangeText={setAllergyName}
              placeholder="Allergen name"
              autoFocus
            />
            <View style={{ gap: Spacing.xs }}>
              <HelperText text="Severity" />
              <View style={{ flexDirection: 'row', gap: Spacing.sm }}>
                {ALLERGY_SEVERITIES.map((s) => (
                  <Pill
                    key={s}
                    label={s}
                    selected={allergySeverity === s}
                    onPress={() => setAllergySeverity(s)}
                    small
                  />
                ))}
              </View>
            </View>
            <FormInput
              value={allergyReaction}
              onChangeText={setAllergyReaction}
              placeholder="Reaction (optional)"
            />
            <PrimaryButton label="Add" onPress={addAllergy} />
          </View>
        )}

        {!noAllergies && !showAllergyEntry && (
          <Pressable
            onPress={() => {
              animateLayout();
              setShowAllergyEntry(true);
              setNoAllergies(false);
            }}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.xs,
              paddingVertical: Spacing.xs,
            }}
          >
            <Icon name="plus" size={18} color={Colors.primary} />
            <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.medium }}>
              Add allergy
            </Text>
          </Pressable>
        )}

        {/* No allergies toggle */}
        <Pressable
          onPress={() => {
            animateLayout();
            const next = !noAllergies;
            setNoAllergies(next);
            if (next) {
              setAllergies([]);
              setShowAllergyEntry(false);
            }
          }}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: Spacing.sm,
            paddingVertical: Spacing.xs,
          }}
        >
          <View
            style={{
              width: 20,
              height: 20,
              borderRadius: 4,
              borderWidth: 1.5,
              borderColor: noAllergies ? Colors.primary : Colors.border,
              backgroundColor: noAllergies ? Colors.primary : 'transparent',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {noAllergies && <Icon name="checkmark-circle" size={14} color={Colors.textInverse} />}
          </View>
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>
            No known allergies
          </Text>
        </Pressable>
      </View>

      <PrimaryButton label="Continue" onPress={onContinue} />
      {onSkip && <SkipButton onPress={onSkip} />}
    </View>
  );
}

// ── Step 4: Health Conditions + Surgical History + Family History ────────────

function Step4Conditions({
  selectedConditions,
  setSelectedConditions,
  showCustomEntry,
  setShowCustomEntry,
  customCondition,
  setCustomCondition,
  surgicalHistory,
  setSurgicalHistory,
  showSurgeryEntry,
  setShowSurgeryEntry,
  surgeryName,
  setSurgeryName,
  surgeryYear,
  setSurgeryYear,
  familyHistory,
  setFamilyHistory,
  onCreateProfile,
  onSkip,
  isPending,
  animateLayout,
  submitLabel,
}: {
  selectedConditions: Map<string, string>;
  setSelectedConditions: React.Dispatch<React.SetStateAction<Map<string, string>>>;
  showCustomEntry: boolean;
  setShowCustomEntry: (v: boolean) => void;
  customCondition: string;
  setCustomCondition: (s: string) => void;
  surgicalHistory: SurgicalProcedure[];
  setSurgicalHistory: React.Dispatch<React.SetStateAction<SurgicalProcedure[]>>;
  showSurgeryEntry: boolean;
  setShowSurgeryEntry: (v: boolean) => void;
  surgeryName: string;
  setSurgeryName: (s: string) => void;
  surgeryYear: string;
  setSurgeryYear: (s: string) => void;
  familyHistory: Record<string, string[]>;
  setFamilyHistory: React.Dispatch<React.SetStateAction<Record<string, string[]>>>;
  onCreateProfile: () => void;
  onSkip?: () => void;
  isPending: boolean;
  animateLayout: () => void;
  submitLabel?: string;
}) {
  const Colors = useColors();

  const addSurgery = () => {
    if (!surgeryName.trim()) return;
    animateLayout();
    const yr = parseInt(surgeryYear, 10);
    setSurgicalHistory((prev) => [
      ...prev,
      { procedure: surgeryName.trim(), year: !isNaN(yr) && yr > 1900 ? yr : undefined },
    ]);
    setSurgeryName('');
    setSurgeryYear('');
    setShowSurgeryEntry(false);
  };

  const removeSurgery = (idx: number) => {
    animateLayout();
    setSurgicalHistory((prev) => prev.filter((_, i) => i !== idx));
  };

  const toggleFamilyCondition = (condition: string) => {
    animateLayout();
    setFamilyHistory((prev) => {
      const next = { ...prev };
      if (next[condition]) {
        delete next[condition];
      } else {
        next[condition] = [];
      }
      return next;
    });
  };

  const toggleFamilyMember = (condition: string, member: string) => {
    setFamilyHistory((prev) => {
      const members = prev[condition] ?? [];
      const next = members.includes(member)
        ? members.filter((m) => m !== member)
        : [...members, member];
      return { ...prev, [condition]: next };
    });
  };

  const toggleCondition = (name: string) => {
    animateLayout();
    setSelectedConditions((prev) => {
      const next = new Map(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.set(name, 'Active');
      }
      return next;
    });
  };

  const setConditionStatus = (name: string, status: string) => {
    setSelectedConditions((prev) => {
      const next = new Map(prev);
      next.set(name, status);
      return next;
    });
  };

  const addCustom = () => {
    if (!customCondition.trim()) return;
    animateLayout();
    setSelectedConditions((prev) => {
      const next = new Map(prev);
      next.set(customCondition.trim(), 'Active');
      return next;
    });
    setCustomCondition('');
    setShowCustomEntry(false);
  };

  const clearAll = () => {
    animateLayout();
    setSelectedConditions(new Map());
  };

  return (
    <View style={{ gap: Spacing.lg }}>
      <View>
        <Text
          style={{
            fontSize: FontSize.xl,
            fontWeight: FontWeight.bold,
            color: Colors.text,
            textAlign: 'center',
          }}
        >
          Health conditions
        </Text>
        <Text
          style={{
            fontSize: FontSize.sm,
            color: Colors.textSecondary,
            textAlign: 'center',
            marginTop: Spacing.xs,
          }}
        >
          Ongoing conditions help give more relevant advice
        </Text>
      </View>

      {/* Common conditions list */}
      <View
        style={{
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
          overflow: 'hidden',
        }}
      >
        {COMMON_CONDITIONS.map((cond, idx) => {
          const isSelected = selectedConditions.has(cond);
          const status = selectedConditions.get(cond);
          return (
            <View key={cond}>
              {idx > 0 && (
                <View style={{ height: 1, backgroundColor: Colors.border, marginHorizontal: Spacing.md }} />
              )}
              <View>
                <Pressable
                  onPress={() => toggleCondition(cond)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    padding: Spacing.md,
                    gap: Spacing.sm,
                  }}
                >
                  <View
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: 4,
                      borderWidth: 1.5,
                      borderColor: isSelected ? Colors.primary : Colors.border,
                      backgroundColor: isSelected ? Colors.primary : 'transparent',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {isSelected && <Icon name="checkmark-circle" size={16} color={Colors.textInverse} />}
                  </View>
                  <Text
                    style={{
                      flex: 1,
                      fontSize: FontSize.md,
                      color: Colors.text,
                      fontWeight: isSelected ? FontWeight.medium : FontWeight.regular,
                    }}
                  >
                    {cond}
                  </Text>
                </Pressable>

                {/* Inline status picker */}
                {isSelected && (
                  <View
                    style={{
                      flexDirection: 'row',
                      gap: Spacing.sm,
                      paddingHorizontal: Spacing.md,
                      paddingBottom: Spacing.sm,
                      marginLeft: Spacing.xl + Spacing.sm,
                    }}
                  >
                    {CONDITION_STATUSES.map((s) => (
                      <Pill
                        key={s}
                        label={s}
                        selected={status === s}
                        onPress={() => setConditionStatus(cond, s)}
                        small
                      />
                    ))}
                  </View>
                )}
              </View>
            </View>
          );
        })}

        {/* Custom conditions that aren't in COMMON_CONDITIONS */}
        {Array.from(selectedConditions.entries())
          .filter(([name]) => !COMMON_CONDITIONS.includes(name as typeof COMMON_CONDITIONS[number]))
          .map(([name, status], idx) => (
            <View key={name}>
              <View style={{ height: 1, backgroundColor: Colors.border, marginHorizontal: Spacing.md }} />
              <View>
                <Pressable
                  onPress={() => toggleCondition(name)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    padding: Spacing.md,
                    gap: Spacing.sm,
                  }}
                >
                  <View
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: 4,
                      borderWidth: 1.5,
                      borderColor: Colors.primary,
                      backgroundColor: Colors.primary,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Icon name="checkmark-circle" size={16} color={Colors.textInverse} />
                  </View>
                  <Text
                    style={{
                      flex: 1,
                      fontSize: FontSize.md,
                      color: Colors.text,
                      fontWeight: FontWeight.medium,
                    }}
                  >
                    {name}
                  </Text>
                </Pressable>
                <View
                  style={{
                    flexDirection: 'row',
                    gap: Spacing.sm,
                    paddingHorizontal: Spacing.md,
                    paddingBottom: Spacing.sm,
                    marginLeft: Spacing.xl + Spacing.sm,
                  }}
                >
                  {CONDITION_STATUSES.map((s) => (
                    <Pill
                      key={s}
                      label={s}
                      selected={status === s}
                      onPress={() => setConditionStatus(name, s)}
                      small
                    />
                  ))}
                </View>
              </View>
            </View>
          ))}
      </View>

      {/* Add another */}
      {showCustomEntry ? (
        <View style={{ flexDirection: 'row', gap: Spacing.sm, alignItems: 'center' }}>
          <View style={{ flex: 1 }}>
            <FormInput
              value={customCondition}
              onChangeText={setCustomCondition}
              placeholder="Condition name"
              autoFocus
              returnKeyType="done"
              onSubmitEditing={addCustom}
            />
          </View>
          <PrimaryButton label="Add" onPress={addCustom} />
        </View>
      ) : (
        <Pressable
          onPress={() => {
            animateLayout();
            setShowCustomEntry(true);
          }}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: Spacing.xs,
          }}
        >
          <Icon name="plus" size={18} color={Colors.primary} />
          <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.medium }}>
            Add another
          </Text>
        </Pressable>
      )}

      {/* None of these */}
      {selectedConditions.size > 0 && (
        <Pressable
          onPress={clearAll}
          style={({ pressed }) => ({
            padding: Spacing.sm,
            alignItems: 'center' as const,
            opacity: pressed ? 0.7 : 1,
          })}
        >
          <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary }}>
            None of these
          </Text>
        </Pressable>
      )}

      {/* Surgical History */}
      <View
        style={{
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
          padding: Spacing.md,
          gap: Spacing.sm,
        }}
      >
        <SectionLabel text="Surgical history" />
        <HelperText text="Past surgeries or procedures" />

        {surgicalHistory.length > 0 && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm }}>
            {surgicalHistory.map((s, i) => (
              <TagChip
                key={`${s.procedure}-${i}`}
                label={s.year ? `${s.procedure} (${s.year})` : s.procedure}
                onRemove={() => removeSurgery(i)}
              />
            ))}
          </View>
        )}

        {showSurgeryEntry ? (
          <View
            style={{
              gap: Spacing.sm,
              backgroundColor: Colors.surface,
              borderRadius: BorderRadius.sm,
              borderCurve: 'continuous',
              padding: Spacing.sm,
            }}
          >
            <FormInput
              value={surgeryName}
              onChangeText={setSurgeryName}
              placeholder="Procedure name"
              autoFocus
            />
            <FormInput
              value={surgeryYear}
              onChangeText={(t) => setSurgeryYear(t.replace(/\D/g, ''))}
              placeholder="Year (optional)"
              keyboardType="number-pad"
              maxLength={4}
            />
            <PrimaryButton label="Add" onPress={addSurgery} />
          </View>
        ) : (
          <Pressable
            onPress={() => {
              animateLayout();
              setShowSurgeryEntry(true);
            }}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: Spacing.xs,
              paddingVertical: Spacing.xs,
            }}
          >
            <Icon name="plus" size={18} color={Colors.primary} />
            <Text style={{ fontSize: FontSize.sm, color: Colors.primary, fontWeight: FontWeight.medium }}>
              Add surgery
            </Text>
          </Pressable>
        )}
      </View>

      {/* Family History */}
      <View
        style={{
          backgroundColor: Colors.surfaceSecondary,
          borderRadius: BorderRadius.md,
          borderCurve: 'continuous',
          borderWidth: 1,
          borderColor: Colors.border,
          padding: Spacing.md,
          gap: Spacing.sm,
        }}
      >
        <SectionLabel text="Family medical history" />
        <HelperText text="Conditions in blood relatives" />

        {FAMILY_CONDITIONS.map((cond) => {
          const isSelected = cond in familyHistory;
          const members = familyHistory[cond] ?? [];
          return (
            <View key={cond}>
              <Pressable
                onPress={() => toggleFamilyCondition(cond)}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: Spacing.sm,
                  paddingVertical: Spacing.xs,
                }}
              >
                <View
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: 4,
                    borderWidth: 1.5,
                    borderColor: isSelected ? Colors.primary : Colors.border,
                    backgroundColor: isSelected ? Colors.primary : 'transparent',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {isSelected && <Icon name="checkmark-circle" size={14} color={Colors.textInverse} />}
                </View>
                <Text style={{ fontSize: FontSize.sm, color: Colors.text }}>
                  {cond}
                </Text>
              </Pressable>
              {isSelected && (
                <View
                  style={{
                    flexDirection: 'row',
                    flexWrap: 'wrap',
                    gap: Spacing.xs,
                    marginLeft: Spacing.xl + Spacing.sm,
                    marginBottom: Spacing.xs,
                  }}
                >
                  {FAMILY_MEMBERS.map((m) => (
                    <Pill
                      key={m}
                      label={m}
                      selected={members.includes(m)}
                      onPress={() => toggleFamilyMember(cond, m)}
                      small
                    />
                  ))}
                </View>
              )}
            </View>
          );
        })}
      </View>

      <PrimaryButton
        label={isPending ? 'Saving...' : (submitLabel ?? 'Create profile')}
        onPress={onCreateProfile}
        disabled={isPending}
      />
      {onSkip && <SkipButton onPress={onSkip} />}
    </View>
  );
}
