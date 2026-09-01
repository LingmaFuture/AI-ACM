import type { Metadata } from "next";

import { ProfileDashboard } from "@/components/ProfileDashboard";

export const metadata: Metadata = { title: "训练档案" };

export default function ProfilePage() { return <ProfileDashboard />; }

