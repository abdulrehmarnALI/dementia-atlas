import AtlasMap from "@/components/AtlasMap";

// the page reads ?level= from the url and hands it to the map
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ level?: string }>;
}) {
  const { level = "sub_icb" } = await searchParams;

  return (
    <main>
      <AtlasMap level={level} />
    </main>
  );
}
