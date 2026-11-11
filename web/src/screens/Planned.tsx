import { EmptyView } from "../components/StateView";

export function Planned({ name }: { name: string }) {
  return (
    <EmptyView title={`${name} llega en una versión posterior`}>
      Esta pantalla todavía no está disponible. Las alertas y la evaluación de la tripulación ya se
      pueden revisar desde Tripulación y Alertas.
    </EmptyView>
  );
}
