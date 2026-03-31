# Precio Diario Gasolina

Seguimiento diario de la **media nacional de precios de carburantes en España**, obtenida directamente desde la API oficial del Ministerio para la Transición Ecológica (MITECO).

## Qué hace

El script `fetch_prices.py` se ejecuta de forma automatizada cada día y:

1. Consulta la API REST del MITECO con los precios en tiempo real de todas las estaciones de servicio terrestres de España.
2. Calcula la **media nacional** para cada tipo de combustible.
3. Añade el resultado al archivo `precios_carburantes.csv` (una fila por día).
4. Genera la gráfica `precios_carburantes.png` con la evolución histórica de precios.

## Combustibles que registra

| Combustible     | Campo API                                  |
|-----------------|--------------------------------------------|
| Gasolina 95 E5  | Precio Gasolina 95 E5                      |
| Gasolina 98 E5  | Precio Gasolina 98 E5                      |
| Diésel          | Precio Gasoleo A                           |
| Diésel Premium  | Precio Gasoleo Premium                     |
| GLP             | Precio Gases licuados del petróleo         |

## Gráfica

La gráfica generada muestra:
- Evolución histórica del precio (€/litro) de cada combustible.
- El **precio actual** de cada combustible anotado al final de su línea.
- La hora a la que se tomó el último dato (hora española).
- Fuente y autoría en el pie de imagen.

## Archivos

| Archivo                    | Descripción                                          |
|----------------------------|------------------------------------------------------|
| `fetch_prices.py`          | Script principal                                     |
| `precios_carburantes.csv`  | Histórico de precios (una fila por día)              |
| `precios_carburantes.png`  | Gráfica de evolución generada automáticamente        |
| `requirements.txt`         | Dependencias Python necesarias                       |

## Requisitos

```
pip install -r requirements.txt
```

Requiere Python 3.9 o superior.

## Uso

```bash
python fetch_prices.py
```

## Fuente de datos

**MITECO** — Ministerio para la Transición Ecológica y el Reto Demográfico  
API: `https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/`

---

Gráfico: [@poloi.eurosky.social](https://bsky.app/profile/poloi.eurosky.social)
